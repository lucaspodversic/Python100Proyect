"""Envío de notificaciones detrás de una interfaz (Protocol).

La lógica de negocio sólo conoce ``Notificador``; en producción se usa
``SMTPNotificador`` y en tests ``FakeNotificador``. La fábrica de conexiones
SMTP también es inyectable para no abrir sockets en los tests.
"""

from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Callable, Protocol


# Protocol = tipado estructural: no hace falta heredar, basta con tener el método ``enviar``.
# Permite sumar Slack/Telegram/webhooks sin tocar el vigilante.
class Notificador(Protocol):
    """Contrato mínimo de cualquier canal de notificación."""

    def enviar(self, asunto: str, cuerpo: str, destinatarios: list[str]) -> None: ...


@dataclass
class SMTPConfig:
    """Parámetros SMTP. Las credenciales se leen de variables de entorno."""

    # Puerto 587 + STARTTLS es la combinación estándar de "submission" autenticado (RFC 6409).
    host: str
    puerto: int = 587
    usuario: str | None = None
    clave: str | None = None
    remitente: str = "alertas@localhost"
    starttls: bool = True

    @classmethod
    def desde_entorno(cls) -> "SMTPConfig":
        """Crea la config desde ``ALERTAS_SMTP_*`` (nunca hardcodear claves)."""
        return cls(
            host=os.environ.get("ALERTAS_SMTP_HOST", "localhost"),
            puerto=int(os.environ.get("ALERTAS_SMTP_PUERTO", "587")),
            usuario=os.environ.get("ALERTAS_SMTP_USUARIO"),
            clave=os.environ.get("ALERTAS_SMTP_CLAVE"),
            remitente=os.environ.get("ALERTAS_SMTP_REMITENTE", "alertas@localhost"),
            # STARTTLS activado por defecto: hay que pedir explícitamente "0" para mandar en claro
            # (p. ej. contra un relay local de pruebas como MailHog en el puerto 1025).
            starttls=os.environ.get("ALERTAS_SMTP_STARTTLS", "1") == "1",
        )


def construir_email(remitente: str, asunto: str, cuerpo: str, destinatarios: list[str]) -> EmailMessage:
    """Crea el objeto EmailMessage (UTF-8, texto plano)."""
    # EmailMessage (API moderna) codifica automáticamente asunto y cuerpo en UTF-8,
    # así las tildes y la ñ llegan bien sin armar MIME a mano.
    msg = EmailMessage()
    msg["From"] = remitente
    # Varios destinatarios en un único encabezado To separado por comas (formato RFC 5322).
    msg["To"] = ", ".join(destinatarios)
    msg["Subject"] = asunto
    msg.set_content(cuerpo)
    return msg


@dataclass
class SMTPNotificador:
    """Implementación real usando ``smtplib``.

    ``fabrica`` recibe (host, puerto) y devuelve un objeto con la API de
    ``smtplib.SMTP`` (context manager, starttls, login, send_message).
    """

    config: SMTPConfig
    # Inyección de dependencias: en producción es ``smtplib.SMTP``; en los tests, una clase falsa
    # con la misma API que registra las llamadas sin abrir sockets.
    fabrica: Callable[[str, int], smtplib.SMTP] = smtplib.SMTP

    def enviar(self, asunto: str, cuerpo: str, destinatarios: list[str]) -> None:
        msg = construir_email(self.config.remitente, asunto, cuerpo, destinatarios)
        # El ``with`` garantiza el QUIT/cierre de la conexión aunque falle el envío.
        with self.fabrica(self.config.host, self.config.puerto) as smtp:
            # Orden obligatorio: primero STARTTLS (cifrar el canal) y DESPUÉS login, para no mandar
            # la contraseña en texto plano.
            if self.config.starttls:
                smtp.starttls()
            # Sin usuario configurado se omite el login (relays internos que autentican por IP).
            if self.config.usuario:
                smtp.login(self.config.usuario, self.config.clave or "")
            smtp.send_message(msg)


@dataclass
class FakeNotificador:
    """Notificador en memoria para tests y para modo ``--dry-run``."""

    # ``default_factory`` evita compartir la misma lista entre instancias (trampa clásica de defaults mutables).
    enviados: list[tuple[str, str, list[str]]] = field(default_factory=list)

    def enviar(self, asunto: str, cuerpo: str, destinatarios: list[str]) -> None:
        # Copiamos la lista de destinatarios para que mutaciones posteriores del llamador no alteren el historial.
        self.enviados.append((asunto, cuerpo, list(destinatarios)))
