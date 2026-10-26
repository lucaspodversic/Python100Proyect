"""Notificadores: consola y webhook JSON (Slack/Discord/ntfy…) con transporte inyectable."""
from __future__ import annotations

import json
import urllib.request
from typing import Callable, Protocol

from .monitor import Cambio

# Un transporte recibe (url, cuerpo JSON en bytes) y devuelve el estado HTTP.
# En tests se reemplaza por una función que anota lo enviado, sin red.
Transporte = Callable[[str, bytes], int]


def transporte_urllib(url: str, cuerpo: bytes) -> int:
    """POST real con la stdlib. Un 4xx/5xx llega como HTTPError (excepción), que sube al llamador."""
    req = urllib.request.Request(url, data=cuerpo, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310 (URL configurada por el usuario)
        return r.status


class Notificador(Protocol):
    """Interfaz común: cualquier objeto con `notificar(cambio)` sirve (duck typing)."""

    def notificar(self, cambio: Cambio) -> None: ...


class NotificadorConsola:
    """Imprime el aviso con el diff. `escribir` inyectable para capturar la salida en tests."""

    def __init__(self, escribir: Callable[[str], None] = print) -> None:
        self.escribir = escribir

    def notificar(self, c: Cambio) -> None:
        self.escribir(f"🔔 Cambió {c.nombre} ({c.url}) +{c.agregadas}/-{c.quitadas} líneas\n{c.diff}")


class NotificadorWebhook:
    """Envía {"text": ...} (formato aceptado por Slack; Discord usa "content")."""

    def __init__(self, url: str, campo: str = "text", transporte: Transporte = transporte_urllib,
                 max_chars: int = 1800) -> None:
        # Los webhooks llevan un secreto en la URL: exigir https evita mandarlo en claro.
        if not url.startswith("https://"):
            raise ValueError("El webhook debe ser https")
        # max_chars: Discord corta en 2000 caracteres; se deja margen para el encabezado.
        self.url, self.campo, self.transporte, self.max = url, campo, transporte, max_chars

    def notificar(self, c: Cambio) -> None:
        # Diffs enormes se recortan y se marca explícitamente que falta contenido.
        diff = c.diff if len(c.diff) <= self.max else c.diff[: self.max] + "\n…(recortado)"
        # *negrita* y ``` bloque de código son Markdown que entienden Slack y Discord.
        texto = f"Cambió *{c.nombre}* {c.url}\n```{diff}```"
        estado = self.transporte(self.url, json.dumps({self.campo: texto}).encode())
        # Slack responde 200 y Discord 204; cualquier 3xx o superior se considera fallo.
        if estado >= 300:
            raise RuntimeError(f"Webhook respondió {estado}")
