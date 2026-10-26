"""Notificadores por webhook (Slack y Discord).

El envío HTTP pasa por `Transporte` (interfaz) para que los tests no
salgan a internet. Las URLs de webhook son secretos: se leen de variables
de entorno, nunca se escriben en el código.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Protocol


# Interfaz mínima: POST de un JSON que devuelve el código HTTP.
class Transporte(Protocol):
    def post_json(self, url: str, cuerpo: dict) -> int: ...


class TransporteHTTP:
    """Transporte real con urllib (timeout corto para no bloquear el bot)."""

    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout

    def post_json(self, url: str, cuerpo: dict) -> int:
        # Sólo HTTPS (el webhook es un secreto y no debe viajar en claro); HTTP se admite sólo hacia localhost para pruebas.
        if not url.startswith(("https://", "http://127.0.0.1", "http://localhost")):
            raise ValueError("El webhook debe usar HTTPS")
        # User-Agent honesto que identifica a esta herramienta.
        req = urllib.request.Request(url, data=json.dumps(cuerpo).encode(), method="POST",
                                     headers={"Content-Type": "application/json",
                                              "User-Agent": "monitor-servidores/1.0"})
        # urlopen lanza HTTPError ante 4xx/5xx; el bot lo captura por canal.
        with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310
            return r.status


class NotificadorSlack:
    """Slack Incoming Webhooks: cuerpo {"text": "..."}."""

    def __init__(self, url: str, transporte: Transporte):
        self.url, self.t = url, transporte

    def enviar(self, texto: str) -> bool:
        # Cualquier 2xx es éxito (Slack responde 200; Discord suele responder 204).
        return 200 <= self.t.post_json(self.url, {"text": texto}) < 300


class NotificadorDiscord:
    """Discord webhooks: cuerpo {"content": "..."} (máx. 2000 caracteres)."""

    def __init__(self, url: str, transporte: Transporte, usuario: str = "Monitor"):
        self.url, self.t, self.usuario = url, transporte, usuario

    def enviar(self, texto: str) -> bool:
        # Se recorta a 2000 caracteres: Discord rechaza mensajes más largos.
        return 200 <= self.t.post_json(self.url, {"content": texto[:2000], "username": self.usuario}) < 300
