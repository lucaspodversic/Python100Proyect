"""Interfaz de proveedores de LLM (modelos de lenguaje).

Todo el proyecto depende SOLO de `ProveedorLLM` (un Protocol), nunca de un SDK
concreto. Así se puede cambiar de OpenAI a Anthropic —o usar el proveedor
falso determinista en los tests— sin tocar la lógica de negocio.

Reglas de seguridad:
- Las claves de API se leen EXCLUSIVAMENTE de variables de entorno
  (OPENAI_API_KEY, ANTHROPIC_API_KEY). Nunca se escriben en el código.
- Los tests no hacen pedidos de red: usan `ProveedorFalso` o un
  `httpx.MockTransport`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, Literal, Protocol

# httpx en vez de los SDK oficiales: una sola dependencia para ambos
# proveedores y, sobre todo, MockTransport permite testear sin red.
import httpx

# Los tres roles que entienden ambas APIs. "system" = instrucciones.
Rol = Literal["system", "user", "assistant"]


# frozen: un mensaje no se modifica después de creado (se puede reusar en
# historiales y registros sin miedo a que cambie).
@dataclass(frozen=True)
class Mensaje:
    """Un mensaje de la conversación."""
    rol: Rol
    contenido: str


# Una sola excepción para todo fallo del proveedor: la lógica de negocio
# captura ErrorLLM y decide cómo degradarse, sin conocer httpx.
class ErrorLLM(RuntimeError):
    """Error al comunicarse con el proveedor (red, autenticación, formato)."""


# Protocol = tipado estructural: cualquier clase con `nombre` y `completar`
# cumple el contrato, sin heredar de nada (por eso el falso de los tests
# es intercambiable con los reales).
class ProveedorLLM(Protocol):
    """Contrato mínimo: recibe mensajes y devuelve el texto generado."""
    nombre: str

    def completar(self, mensajes: list[Mensaje], *, temperatura: float = 0.0, max_tokens: int = 512) -> str: ...


def _clave(variable: str) -> str:
    """Lee una clave de API del entorno o falla con un mensaje claro."""
    # La clave se lee en el momento de usarla (no al importar): así se puede
    # crear el proveedor sin clave y el error aparece recién al llamar, con un
    # mensaje que dice qué variable falta. Nunca se loguea ni se devuelve.
    valor = os.environ.get(variable, "").strip()
    if not valor:
        raise ErrorLLM(f"Falta la variable de entorno {variable}")
    return valor


class ProveedorOpenAI:
    """Cliente mínimo de la API Chat Completions de OpenAI (vía httpx)."""
    nombre = "openai"

    def __init__(self, modelo: str | None = None, cliente: httpx.Client | None = None,
                 url_base: str = "https://api.openai.com/v1") -> None:
        # Modelo configurable por entorno; por defecto uno barato y rápido.
        self.modelo = modelo or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        # rstrip("/") evita URLs con doble barra si se pasa ".../v1/".
        self.url_base = url_base.rstrip("/")
        self._cliente = cliente  # inyectable para tests (MockTransport)

    def completar(self, mensajes: list[Mensaje], *, temperatura: float = 0.0, max_tokens: int = 512) -> str:
        # Formato Chat Completions: todos los mensajes (incluido system) en una lista.
        cuerpo = {"model": self.modelo, "temperature": temperatura, "max_tokens": max_tokens,
                  "messages": [{"role": m.rol, "content": m.contenido} for m in mensajes]}
        cabeceras = {"Authorization": f"Bearer {_clave('OPENAI_API_KEY')}"}
        # Si no se inyectó un cliente se crea uno por llamada con timeout de 60 s
        # (un LLM puede tardar, pero nunca hay que esperar para siempre).
        cliente = self._cliente or httpx.Client(timeout=60)
        try:
            r = cliente.post(f"{self.url_base}/chat/completions", json=cuerpo, headers=cabeceras)
            # 4xx/5xx => httpx.HTTPStatusError => se convierte en ErrorLLM abajo.
            r.raise_for_status()
            # `or ""`: la API puede devolver content null (p. ej. con tool calls).
            return r.json()["choices"][0]["message"]["content"] or ""
        # Red/HTTP, JSON con otra forma (KeyError/IndexError) o JSON inválido
        # (ValueError): todo se reporta como ErrorLLM conservando la causa.
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            raise ErrorLLM(f"OpenAI falló: {e}") from e
        finally:
            # Solo se cierra el cliente si lo creamos acá; uno inyectado es del llamador.
            if self._cliente is None:
                cliente.close()


class ProveedorAnthropic:
    """Cliente mínimo de la API Messages de Anthropic (vía httpx).

    Diferencia clave con OpenAI: el mensaje de sistema va en un campo aparte
    (`system`) y la respuesta es una lista de bloques de contenido.
    """
    nombre = "anthropic"

    def __init__(self, modelo: str | None = None, cliente: httpx.Client | None = None,
                 url_base: str = "https://api.anthropic.com/v1") -> None:
        self.modelo = modelo or os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-latest")
        self.url_base = url_base.rstrip("/")
        self._cliente = cliente

    def completar(self, mensajes: list[Mensaje], *, temperatura: float = 0.0, max_tokens: int = 512) -> str:
        # Anthropic no acepta rol "system" en la lista: se juntan todos los de
        # sistema en el campo `system` y el resto va en `messages`.
        sistema = "\n".join(m.contenido for m in mensajes if m.rol == "system")
        cuerpo: dict = {"model": self.modelo, "max_tokens": max_tokens, "temperature": temperatura,
                        "messages": [{"role": m.rol, "content": m.contenido} for m in mensajes if m.rol != "system"]}
        if sistema:
            cuerpo["system"] = sistema
        # Anthropic autentica con x-api-key y exige fijar la versión de la API.
        cabeceras = {"x-api-key": _clave("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01"}
        cliente = self._cliente or httpx.Client(timeout=60)
        try:
            r = cliente.post(f"{self.url_base}/messages", json=cuerpo, headers=cabeceras)
            r.raise_for_status()
            # La respuesta es una lista de bloques; se concatenan solo los de texto.
            return "".join(b.get("text", "") for b in r.json()["content"] if b.get("type") == "text")
        except (httpx.HTTPError, KeyError, ValueError) as e:
            raise ErrorLLM(f"Anthropic falló: {e}") from e
        finally:
            if self._cliente is None:
                cliente.close()


@dataclass
class ProveedorFalso:
    """Proveedor determinista para tests y demos sin conexión.

    - `respuestas`: lista de textos que se devuelven en orden (cíclico), o
    - `funcion`: callable que recibe los mensajes y arma la respuesta.
    Registra cada llamada en `llamadas` para poder verificar los prompts.
    """
    # default_factory: cada instancia tiene su propia lista (evita compartir
    # un default mutable entre instancias).
    respuestas: list[str] = field(default_factory=lambda: ["respuesta falsa"])
    funcion: Callable[[list[Mensaje]], str] | None = None
    nombre: str = "falso"
    llamadas: list[list[Mensaje]] = field(default_factory=list)

    def completar(self, mensajes: list[Mensaje], *, temperatura: float = 0.0, max_tokens: int = 512) -> str:
        # Se guarda una copia: si el llamador modifica su lista después, el
        # registro de lo que se envió no cambia.
        self.llamadas.append(list(mensajes))
        if self.funcion:
            return self.funcion(mensajes)
        # Índice cíclico: con ["a", "b"] las llamadas devuelven a, b, a, b...
        return self.respuestas[(len(self.llamadas) - 1) % len(self.respuestas)]


def crear_proveedor(nombre: str | None = None) -> ProveedorLLM:
    """Fábrica según `nombre` o la variable LLM_PROVEEDOR (openai | anthropic | falso)."""
    # Por defecto "falso": el proyecto funciona de entrada sin claves ni red.
    nombre = (nombre or os.environ.get("LLM_PROVEEDOR", "falso")).lower()
    if nombre == "openai":
        return ProveedorOpenAI()
    if nombre == "anthropic":
        return ProveedorAnthropic()
    if nombre == "falso":
        return ProveedorFalso()
    # Mejor fallar fuerte que usar en silencio otro proveedor.
    raise ValueError(f"Proveedor desconocido: {nombre}")
