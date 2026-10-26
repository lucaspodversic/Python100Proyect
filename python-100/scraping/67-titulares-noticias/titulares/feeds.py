"""Parser de RSS 2.0 y Atom 1.0 con la biblioteca estándar.

Los feeds son la vía oficial que ofrecen los medios para reutilizar titulares,
por eso se prefieren a scrapear el HTML de portada.

Seguridad: se rechazan documentos con DOCTYPE/ENTITY para evitar ataques de
expansión de entidades (XXE / "billion laughs"); los feeds legítimos no los usan.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape

# ElementTree escribe las etiquetas con namespace como "{uri}etiqueta".
ATOM = "{http://www.w3.org/2005/Atom}"
# Regex simple para quitar etiquetas HTML de los resúmenes (no se interpreta el HTML, sólo se descarta).
_ETIQUETAS = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class Noticia:
    """Un titular normalizado, independiente del formato de origen."""

    titulo: str
    enlace: str
    fuente: str                 # nombre del medio (título del canal/feed)
    fecha: datetime | None      # siempre con zona horaria (aware) o None si no se pudo leer
    resumen: str = ""           # texto plano, sin HTML, recortado


def _fecha(texto: str | None) -> datetime | None:
    """RSS usa RFC 822 ('Mon, 26 Oct 2026 10:00:00 GMT'); Atom usa ISO 8601."""
    if not texto:
        return None
    texto = texto.strip()
    try:
        # Primero RFC 822 (RSS).
        d = parsedate_to_datetime(texto)
    except (TypeError, ValueError):
        try:
            # Luego ISO 8601 (Atom). "Z" se reemplaza porque fromisoformat no lo acepta en Python < 3.11.
            d = datetime.fromisoformat(texto.replace("Z", "+00:00"))
        except ValueError:
            return None     # caso borde: fecha ilegible → la noticia se conserva sin fecha
    # Fechas sin zona se asumen UTC, para poder comparar y ordenar con las demás.
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _limpio(html: str | None, max_chars: int = 240) -> str:
    """Quita etiquetas, decodifica entidades (&amp; → &), colapsa espacios y recorta con '…'."""
    t = " ".join(unescape(_ETIQUETAS.sub(" ", html or "")).split())
    return t if len(t) <= max_chars else t[: max_chars - 1].rstrip() + "…"


def parsear_feed(contenido: bytes | str, fuente: str = "") -> list[Noticia]:
    """Detecta el formato (Atom o RSS) y devuelve las noticias con título.

    `fuente` permite forzar el nombre del medio; si no, se usa el título del feed.
    Lanza ValueError ante formatos desconocidos o XML con DOCTYPE/ENTITY.
    """
    datos = contenido.encode() if isinstance(contenido, str) else contenido
    # Defensa XXE/billion laughs: el DOCTYPE va al principio, basta mirar los primeros 4 KB.
    if re.search(rb"<!(DOCTYPE|ENTITY)", datos[:4096], re.I):
        raise ValueError("Feed con DOCTYPE/ENTITY rechazado por seguridad")
    raiz = ET.fromstring(datos)
    noticias: list[Noticia] = []
    if raiz.tag == f"{ATOM}feed":
        # --- Atom 1.0 ---
        nombre = fuente or (raiz.findtext(f"{ATOM}title") or "").strip()
        for e in raiz.iter(f"{ATOM}entry"):
            # Se prefiere el enlace rel="alternate" (o sin rel) frente a "self"/"edit".
            enlaces = [l for l in e.findall(f"{ATOM}link") if l.get("rel", "alternate") == "alternate"]
            noticias.append(Noticia((e.findtext(f"{ATOM}title") or "").strip(),
                                    enlaces[0].get("href", "") if enlaces else "", nombre,
                                    # updated es obligatorio en Atom; published es opcional (respaldo).
                                    _fecha(e.findtext(f"{ATOM}updated") or e.findtext(f"{ATOM}published")),
                                    _limpio(e.findtext(f"{ATOM}summary") or e.findtext(f"{ATOM}content"))))
    elif raiz.tag == "rss" or raiz.find("channel") is not None:
        # --- RSS 2.0 (y variantes sin la raíz <rss> pero con <channel>) ---
        canal = raiz.find("channel")
        nombre = fuente or (canal.findtext("title") or "").strip()
        for it in canal.iter("item"):
            noticias.append(Noticia((it.findtext("title") or "").strip(), (it.findtext("link") or "").strip(),
                                    nombre, _fecha(it.findtext("pubDate")), _limpio(it.findtext("description"))))
    else:
        raise ValueError(f"Formato de feed no reconocido: {raiz.tag}")
    # Ítems sin título no sirven para un resumen de titulares.
    return [n for n in noticias if n.titulo]
