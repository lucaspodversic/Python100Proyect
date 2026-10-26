"""Capa HTTP (FastAPI) del gateway.

Endpoints:
  POST /v1/chat     -> {"modelo": alias, "mensajes": [{rol, contenido}], ...}
  GET  /v1/modelos  -> aliases disponibles
  GET  /v1/uso      -> consumo de la clave que consulta
  GET  /salud       -> estado y estadísticas de caché (sin auth)

Autenticación: `Authorization: Bearer <clave>`. Las claves válidas vienen de la
variable GATEWAY_CLAVES (separadas por coma) y se guardan solo como SHA-256.
Las claves de los proveedores (OpenAI/Anthropic) nunca llegan al cliente.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from gateway.llm import Mensaje, ProveedorAnthropic, ProveedorFalso, ProveedorOpenAI
from gateway.nucleo import Gateway, LimitadorTasa, Ruta, SinProveedores


class MensajeIn(BaseModel):
    rol: Literal["system", "user", "assistant"]
    contenido: str = Field(min_length=1, max_length=50_000)


# Límites de validación para proteger al gateway y al bolsillo: hasta 100
# mensajes de 50.000 caracteres, temperatura 0..2 y hasta 4096 tokens.
class PedidoChat(BaseModel):
    modelo: str = "defecto"
    mensajes: list[MensajeIn] = Field(min_length=1, max_length=100)
    temperatura: float = Field(default=0.0, ge=0, le=2)
    max_tokens: int = Field(default=512, ge=1, le=4096)


# Las claves de clientes se guardan hasheadas: si alguien vuelca la memoria
# o un log de configuración, no ve las claves en claro.
def _hash(clave: str) -> str:
    return hashlib.sha256(clave.encode()).hexdigest()


def crear_app(gateway: Gateway, claves: list[str], limitador: LimitadorTasa | None = None) -> FastAPI:
    app = FastAPI(title="Gateway LLM")
    # `if c` descarta vacías (GATEWAY_CLAVES="" da [""] al hacer split).
    hashes = {_hash(c): f"cliente-{i}" for i, c in enumerate(claves) if c}
    limitador = limitador or LimitadorTasa(por_minuto=60)

    def autenticar(authorization: str = Header(default="")) -> str:
        # removeprefix (Python 3.9+) no falla si el prefijo no está.
        token = authorization.removeprefix("Bearer ").strip()
        h = _hash(token)
        # compare_digest contra cada hash: tiempo constante por comparación
        for hv, cliente in hashes.items():
            if hmac.compare_digest(h, hv):
                return cliente
        raise HTTPException(401, "Clave inválida", headers={"WWW-Authenticate": "Bearer"})

    # Sin auth a propósito: lo consultan balanceadores y monitoreo. No expone
    # datos de clientes, solo aliases y contadores de caché.
    @app.get("/salud")
    def salud():
        c = gateway.cache
        return {"ok": True, "modelos": list(gateway.rutas), "cache": {"aciertos": c.aciertos, "fallos": c.fallos}}

    @app.get("/v1/modelos")
    def modelos(cliente: str = Depends(autenticar)):
        return [{"alias": a, "proveedores": [p.nombre for p in r.proveedores]} for a, r in gateway.rutas.items()]

    @app.get("/v1/uso")
    def uso(cliente: str = Depends(autenticar)):
        return {"cliente": cliente, **gateway.uso[cliente]}

    @app.post("/v1/chat")
    def chat(p: PedidoChat, cliente: str = Depends(autenticar)):
        # Límite por cliente; Retry-After le sugiere cuándo reintentar.
        if not limitador.permitir(cliente):
            raise HTTPException(429, "Demasiados pedidos", headers={"Retry-After": "1"})
        try:
            return gateway.chat(cliente, p.modelo, [Mensaje(m.rol, m.contenido) for m in p.mensajes],
                                p.temperatura, p.max_tokens)
        # El núcleo lanza KeyError para alias inexistentes => 404.
        except KeyError:
            raise HTTPException(404, f"Modelo desconocido: {p.modelo}") from None
        except SinProveedores as e:
            # No se filtran detalles internos completos: solo cuántos intentos fallaron
            raise HTTPException(502, f"Todos los proveedores fallaron ({len(e.errores)} intentos)") from None

    return app


def gateway_desde_entorno() -> Gateway:
    """Arma las rutas según qué claves de proveedor existan en el entorno."""
    rutas: dict[str, Ruta] = {}
    # El orden de la cadena define el fallback: primero OpenAI, luego Anthropic.
    # Sin ninguna clave se usa el proveedor falso, así arranca igual en demo.
    cadena = []
    if os.environ.get("OPENAI_API_KEY"):
        cadena.append(ProveedorOpenAI())
    if os.environ.get("ANTHROPIC_API_KEY"):
        cadena.append(ProveedorAnthropic())
    rutas["defecto"] = Ruta(cadena or [ProveedorFalso()], costo_por_1k=0.0005)
    # "eco" devuelve el último mensaje: útil para probar el gateway sin LLM.
    rutas["eco"] = Ruta([ProveedorFalso(funcion=lambda ms: ms[-1].contenido, nombre="eco")])
    return Gateway(rutas)


# `uvicorn gateway.app:app` -> claves desde GATEWAY_CLAVES
app = crear_app(gateway_desde_entorno(), os.environ.get("GATEWAY_CLAVES", "").split(","))
