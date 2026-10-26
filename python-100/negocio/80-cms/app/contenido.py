"""Utilidades puras de contenido: slugs, render seguro y validación de imágenes."""
from __future__ import annotations

import html
import re
import unicodedata
from collections.abc import Callable

MAX_IMAGEN = 2 * 1024 * 1024  # 2 MiB

#: Firmas ("números mágicos") de los formatos aceptados → (tipo MIME, extensión).
FIRMAS: list[tuple[bytes, str, str]] = [
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"GIF87a", "image/gif", "gif"),
    (b"GIF89a", "image/gif", "gif"),
]


def slugificar(texto: str) -> str:
    """"¡Hola, Año Nuevo!" → "hola-ano-nuevo" (sin tildes, minúsculas, guiones)."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", sin_tildes.lower()).strip("-")
    return slug[:200] or "articulo"


def slug_unico(base: str, existe: Callable[[str], bool]) -> str:
    """Agrega -2, -3… hasta encontrar un slug libre según ``existe(slug)``."""
    slug, n = base, 2
    while existe(slug):
        slug, n = f"{base}-{n}", n + 1
    return slug


def detectar_imagen(datos: bytes) -> tuple[str, str] | None:
    """Detecta el formato por el contenido real (no por la extensión ni el Content-Type)."""
    for firma, mime, ext in FIRMAS:
        if datos.startswith(firma):
            return mime, ext
    return None


def renderizar(cuerpo: str) -> str:
    """Markdown mínimo → HTML **seguro**.

    Primero se escapa todo el HTML del autor (evita XSS) y después se aplican
    solo transformaciones conocidas: ``# títulos``, ``**negrita**``,
    ``*cursiva*``, ``[texto](https://url)`` y párrafos.
    """
    bloques = []
    for bloque in re.split(r"\n\s*\n", cuerpo.strip()):
        b = html.escape(bloque.strip())
        m = re.match(r"^(#{1,3}) (.+)$", b)
        if m:
            nivel = len(m.group(1))
            bloques.append(f"<h{nivel}>{m.group(2)}</h{nivel}>")
            continue
        b = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", b)
        b = re.sub(r"\*(.+?)\*", r"<em>\1</em>", b)
        # Solo enlaces http(s): bloquea esquemas peligrosos como javascript:
        b = re.sub(r"\[([^\]]+)\]\((https?://[^\s)\"]+)\)", r'<a href="\2" rel="nofollow">\1</a>', b)
        bloques.append(f"<p>{b.replace(chr(10), '<br>')}</p>")
    return "\n".join(bloques)
