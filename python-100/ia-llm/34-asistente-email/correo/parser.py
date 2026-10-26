"""Lectura de correos .eml con la biblioteca estándar `email`.

Se usa `policy.default`, que decodifica encabezados (=?utf-8?...?=) y
contenido automáticamente. Si el correo solo trae HTML, se convierte a texto.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path


class _HTMLaTexto(HTMLParser):
    """Conversor HTML -> texto mínimo (ignora <script>/<style>)."""

    def __init__(self) -> None:
        super().__init__()
        self.partes: list[str] = []
        # Contador (no bool) por si hay <script> anidados o mal cerrados.
        self._ignorar = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._ignorar += 1
        # Etiquetas de bloque => salto de línea, para no pegar párrafos.
        elif tag in ("br", "p", "div", "li", "tr"):
            self.partes.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._ignorar -= 1

    def handle_data(self, data):
        if not self._ignorar:
            self.partes.append(data)


def html_a_texto(html: str) -> str:
    p = _HTMLaTexto(); p.feed(html)
    # Colapsa líneas vacías repetidas en una sola separación.
    return re.sub(r"\n\s*\n+", "\n\n", "".join(p.partes)).strip()


def quitar_citas(texto: str) -> str:
    """Elimina el historial citado ('> ...' y 'El ... escribió:') para no resumirlo dos veces."""
    lineas = []
    for l in texto.splitlines():
        # Encabezado de cita de Gmail/Outlook (español o inglés): todo lo que sigue
        # es historial, así que se corta ahí.
        if re.match(r"^\s*(El|On) .+(escribió|wrote):\s*$", l):
            break
        if not l.lstrip().startswith(">"):
            lineas.append(l)
    return "\n".join(lineas).strip()


@dataclass
class Correo:
    asunto: str
    remitente: tuple[str, str]           # (nombre, dirección)
    destinatarios: list[tuple[str, str]]
    fecha: str | None
    message_id: str | None
    referencias: str
    cuerpo: str
    adjuntos: list[str] = field(default_factory=list)


def leer_eml(origen: str | Path | bytes) -> Correo:
    datos = origen if isinstance(origen, bytes) else Path(origen).read_bytes()
    msg: EmailMessage = BytesParser(policy=policy.default).parsebytes(datos)  # type: ignore[assignment]
    # Prefiere texto plano; si solo hay HTML, se lo convierte a texto.
    parte = msg.get_body(preferencelist=("plain", "html"))
    cuerpo = ""
    if parte is not None:
        cuerpo = parte.get_content()
        if parte.get_content_type() == "text/html":
            cuerpo = html_a_texto(cuerpo)
    # Solo se listan los nombres: el contenido de los adjuntos no se procesa.
    adjuntos = [a.get_filename() or "sin_nombre" for a in msg.iter_attachments()]
    remitentes = getaddresses([msg.get("From", "")])
    fecha = None
    if msg.get("Date"):
        try:
            fecha = parsedate_to_datetime(msg["Date"]).isoformat()
        # Fecha malformada: se deja en None en vez de fallar toda la lectura.
        except (TypeError, ValueError):
            pass
    # getaddresses devuelve pares (nombre, dirección) ya decodificados.
    return Correo(asunto=str(msg.get("Subject", "")), remitente=remitentes[0] if remitentes else ("", ""),
                  destinatarios=getaddresses(msg.get_all("To", []) + msg.get_all("Cc", [])), fecha=fecha,
                  message_id=msg.get("Message-ID"), referencias=str(msg.get("References", "")),
                  cuerpo=quitar_citas(cuerpo), adjuntos=adjuntos)
