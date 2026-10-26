"""CLI: memes imagen.jpg -a "TEXTO ARRIBA" -b "TEXTO ABAJO" -o meme.jpg"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from PIL import Image, UnidentifiedImageError

from .componer import EstiloMeme, crear_meme


def ejecutar(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="memes")
    p.add_argument("imagen", type=Path)
    p.add_argument("-a", "--arriba", default="")
    p.add_argument("-b", "--abajo", default="")
    p.add_argument("-o", "--salida", type=Path)
    p.add_argument("--fuente", help="ruta a un .ttf")
    # Por defecto el texto se pasa a MAYÚSCULAS, como en los memes clásicos.
    p.add_argument("--sin-mayusculas", action="store_true")
    a = p.parse_args(argv)
    # Caso borde: sin texto no hay meme → exit 2 (uso incorrecto, como argparse).
    if not (a.arriba or a.abajo):
        print("Indicá al menos -a o -b", file=sys.stderr); return 2
    try:
        img = Image.open(a.imagen)
    # Archivo inexistente o que no es una imagen → exit 1.
    except (OSError, UnidentifiedImageError) as exc:
        print(f"No se pudo abrir la imagen: {exc}", file=sys.stderr); return 1
    meme = crear_meme(img, a.arriba, a.abajo, EstiloMeme(not a.sin_mayusculas, ruta_fuente=a.fuente))
    # Por defecto: foto.png → foto_meme.jpg en la misma carpeta.
    salida = a.salida or a.imagen.with_name(a.imagen.stem + "_meme.jpg")
    # quality=92: buen equilibrio entre nitidez del texto y peso del JPG.
    meme.save(salida, quality=92)
    print(f"Meme guardado en {salida}")
    return 0


def main() -> None:
    sys.exit(ejecutar())
