"""Anotación de imágenes con Pillow: cajas de color estable por clase y etiqueta con confianza."""
from __future__ import annotations

import hashlib

from PIL import Image, ImageDraw

from .modelo import Deteccion


def color_clase(clase: str) -> tuple[int, int, int]:
    """Color determinista (mismo nombre → mismo color) y no demasiado oscuro."""
    h = hashlib.md5(clase.encode()).digest()
    return tuple(80 + b % 176 for b in h[:3])  # type: ignore[return-value]


def anotar(imagen: Image.Image, dets: list[Deteccion], grosor: int = 2) -> Image.Image:
    """Devuelve una COPIA de la imagen con una caja por detección y una etiqueta 'clase NN%'
    con fondo del color de la clase. La etiqueta va arriba de la caja si entra, y si no
    adentro (cajas pegadas al borde superior). x2/y2 son exclusivos, por eso se dibuja
    hasta x2-1.
    """
    out = imagen.convert("RGB").copy()
    d = ImageDraw.Draw(out)
    for det in dets:
        c = det.caja
        col = color_clase(det.clase)
        d.rectangle([c.x1, c.y1, c.x2 - 1, c.y2 - 1], outline=col, width=grosor)
        texto = f"{det.clase} {det.confianza:.0%}"
        x0, y0, x1, y1 = d.textbbox((c.x1, c.y1), texto)
        ty = c.y1 - (y1 - y0) - 2 if c.y1 - (y1 - y0) - 2 >= 0 else c.y1   # arriba de la caja si entra
        d.rectangle([c.x1, ty, c.x1 + (x1 - x0) + 4, ty + (y1 - y0) + 2], fill=col)
        d.text((c.x1 + 2, ty), texto, fill=(0, 0, 0))
    return out
