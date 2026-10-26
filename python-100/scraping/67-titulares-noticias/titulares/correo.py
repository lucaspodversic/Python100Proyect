"""Envío por email detrás de una interfaz: en tests se usa un SMTP falso."""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from typing import Callable, Protocol


def armar_mensaje(remitente: str, destinatarios: list[str], asunto: str, texto: str, html: str | None) -> EmailMessage:
    """Mensaje multipart/alternative: texto plano + HTML (el cliente de correo elige cuál mostrar)."""
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = remitente, ", ".join(destinatarios), asunto
    m.set_content(texto)
    if html:
        # add_alternative convierte el mensaje en multipart y agrega la versión HTML.
        m.add_alternative(html, subtype="html")
    return m


class Enviador(Protocol):
    """Interfaz de envío: permite cambiar SMTP por un fake, una API de email o la consola."""

    def enviar(self, mensaje: EmailMessage) -> None: ...


class EnviadorSMTP:
    """SMTP con STARTTLS. La contraseña se recibe (p. ej. de una variable de entorno), nunca se guarda."""

    def __init__(self, host: str, puerto: int = 587, usuario: str | None = None, clave: str | None = None,
                 fabrica: Callable[..., smtplib.SMTP] = smtplib.SMTP) -> None:
        # `fabrica` es inyectable: en tests se pasa una clase falsa con la misma interfaz que smtplib.SMTP.
        self.host, self.puerto, self.usuario, self.clave, self.fabrica = host, puerto, usuario, clave, fabrica

    def enviar(self, mensaje: EmailMessage) -> None:
        # `with` garantiza QUIT y cierre de la conexión aunque falle el envío.
        with self.fabrica(self.host, self.puerto, timeout=20) as s:
            # STARTTLS con verificación de certificado ANTES de mandar credenciales.
            s.starttls(context=ssl.create_default_context())
            if self.usuario:
                s.login(self.usuario, self.clave or "")
            s.send_message(mensaje)


class EnviadorConsola:
    """Alternativa sin servidor: imprime el cuerpo en texto plano (útil para probar)."""

    def enviar(self, mensaje: EmailMessage) -> None:
        print(mensaje.get_body(("plain",)).get_content())
