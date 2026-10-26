"""Canales de alerta: consola, webhook (Slack/Discord/Teams) y fake para tests."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Protocol


# Protocol (tipado estructural): cualquier objeto con notificar(str) sirve, sin heredar.
class Notificador(Protocol):
    def notificar(self, mensaje: str) -> None: ...


class ConsolaNotificador:
    def notificar(self, mensaje: str) -> None:
        print(f"🔔 {mensaje}")


# Envío real por HTTP POST con JSON; timeout para que un webhook caído no cuelgue el monitor.
def _post_json(url: str, cuerpo: dict[str, str]) -> None:  # pragma: no cover - red real
    req = urllib.request.Request(url, data=json.dumps(cuerpo).encode(), headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10).close()  # noqa: S310


@dataclass
class WebhookNotificador:
    """Webhook entrante (formato ``{"text": ...}`` compatible con Slack; Discord usa ``content``)."""

    url: str
    # Slack/Teams usan "text"; para Discord se configura campo="content".
    campo: str = "text"
    # Función de envío inyectable: los tests capturan el payload sin hacer red.
    enviar: Callable[[str, dict[str, str]], None] = _post_json

    def notificar(self, mensaje: str) -> None:
        self.enviar(self.url, {self.campo: mensaje})


@dataclass
class FakeNotificador:
    mensajes: list[str] = field(default_factory=list)

    def notificar(self, mensaje: str) -> None:
        self.mensajes.append(mensaje)
