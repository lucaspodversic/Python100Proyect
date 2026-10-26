"""API de la pasarela de pagos simulada.

Los comercios se registran (rol ``comercio``), configuran su webhook y operan
con su token. Las operaciones que mueven dinero exigen ``Idempotency-Key``.
"""
from __future__ import annotations

import secrets
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import servicio
from .auth import crear_auth
from .db import Base, crear_fabrica_sesiones, crear_motor
from .modelos import ConfigWebhook, Evento, Pago, Rol, Token, Usuario
from .servicio import ErrorNegocio, Transporte


class TarjetaIn(BaseModel):
    numero: str = Field(min_length=12, max_length=23)
    mes: int = Field(ge=1, le=12)
    anio: int = Field(ge=2000, le=2100)


class PagoIn(BaseModel):
    monto_centavos: int = Field(gt=0, le=10_000_000_00)
    moneda: str = Field(min_length=3, max_length=3)
    tarjeta: TarjetaIn
    descripcion: str = Field(default="", max_length=300)


class ReembolsoIn(BaseModel):
    monto_centavos: int | None = Field(default=None, gt=0)
    motivo: str = Field(default="", max_length=200)


class WebhookIn(BaseModel):
    url: str = Field(pattern=r"^https?://", max_length=500)


def transporte_http(url: str, cabeceras: dict[str, str], cuerpo: bytes) -> int:  # pragma: no cover - red real
    """Transporte por defecto con la biblioteca estándar (no se usa en tests)."""
    req = urllib.request.Request(url, data=cuerpo, headers=cabeceras, method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def crear_app(url_bd: str = "sqlite:///pagos.db", transporte: Transporte = transporte_http,
              reloj: Callable[[], datetime] = ahora_utc) -> FastAPI:
    """Fábrica de la aplicación; ``transporte`` y ``reloj`` son inyectables."""
    app = FastAPI(title="Pasarela de pagos (simulada)", version="1.0.0")
    motor = crear_motor(url_bd)
    Base.metadata.create_all(motor)
    app.state.fabrica = crear_fabrica_sesiones(motor)
    auth = crear_auth(app.state.fabrica, Usuario, Token, Rol.COMERCIO)
    app.include_router(auth.router)
    S = Depends(auth.obtener_sesion)
    comercio = Depends(auth.requiere_rol(Rol.COMERCIO))

    @app.exception_handler(ErrorNegocio)
    async def _err(_r: Request, e: ErrorNegocio) -> JSONResponse:
        return JSONResponse(status_code=e.codigo, content={"detail": e.mensaje})

    def responder(codigo: int, datos: dict, repetida: bool) -> JSONResponse:
        # La cabecera avisa al cliente que es una respuesta reproducida.
        return JSONResponse(status_code=codigo, content=datos,
                            headers={"Idempotent-Replayed": "true" if repetida else "false"})

    @app.post("/webhook")
    def configurar_webhook(d: WebhookIn, u: Usuario = comercio, s: Session = S) -> dict:
        """Configura (o rota) el secreto. Se muestra **una sola vez**."""
        secreto = "whsec_" + secrets.token_hex(24)
        cfg = s.get(ConfigWebhook, u.id)
        if cfg is None:
            s.add(ConfigWebhook(usuario_id=u.id, url=d.url, secreto=secreto))
        else:
            cfg.url, cfg.secreto = d.url, secreto
        return {"url": d.url, "secreto": secreto}

    @app.post("/pagos")
    def crear_pago(d: PagoIn, idempotency_key: str = Header(alias="Idempotency-Key"),
                   u: Usuario = comercio, s: Session = S) -> JSONResponse:
        ahora = reloj()
        return responder(*servicio.con_idempotencia(
            s, u, idempotency_key, servicio.huella("/pagos", d.model_dump()), ahora,
            lambda: servicio.cobrar(s, u, d.monto_centavos, d.moneda, d.tarjeta.numero, d.tarjeta.mes,
                                    d.tarjeta.anio, d.descripcion, ahora)))

    @app.get("/pagos")
    def listar(u: Usuario = comercio, s: Session = S) -> list[dict]:
        return [servicio.pago_dict(p) for p in s.scalars(select(Pago).where(Pago.comercio_id == u.id).order_by(Pago.id))]

    @app.get("/pagos/{publico}")
    def ver(publico: str, u: Usuario = comercio, s: Session = S) -> dict:
        return servicio.pago_dict(servicio.pago_de(s, u, publico))

    @app.post("/pagos/{publico}/reembolsos")
    def reembolsar(publico: str, d: ReembolsoIn, idempotency_key: str = Header(alias="Idempotency-Key"),
                   u: Usuario = comercio, s: Session = S) -> JSONResponse:
        ahora = reloj()
        ruta = f"/pagos/{publico}/reembolsos"
        return responder(*servicio.con_idempotencia(
            s, u, idempotency_key, servicio.huella(ruta, d.model_dump()), ahora,
            lambda: servicio.reembolsar(s, u, publico, d.monto_centavos, d.motivo, ahora)))

    @app.get("/eventos")
    def eventos(u: Usuario = comercio, s: Session = S) -> list[dict]:
        evs = s.scalars(select(Evento).where(Evento.comercio_id == u.id).order_by(Evento.id))
        return [{"id": e.publico, "tipo": e.tipo, "entregado": e.entregado, "intentos": e.intentos,
                 "ultimo_error": e.ultimo_error} for e in evs]

    @app.post("/eventos/despachar")
    def despachar(u: Usuario = comercio, s: Session = S) -> dict:
        return servicio.despachar(s, u.id, transporte, int(reloj().replace(tzinfo=timezone.utc).timestamp()))

    return app


def __getattr__(nombre: str):  # pragma: no cover
    if nombre == "app":
        return crear_app()
    raise AttributeError(nombre)
