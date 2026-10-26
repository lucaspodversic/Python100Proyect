"""CLI: audiolibro libro.pdf -o libro.mp3 [--idioma es] [--desde 1 --hasta 10]."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .convertidor import Convertidor, MotorGTTS, MotorVoz


# `motor` inyectable: los tests usan uno falso y nunca llaman al servicio de Google.
def ejecutar(argv: Sequence[str] | None = None, motor: MotorVoz | None = None) -> int:
    p = argparse.ArgumentParser(prog="audiolibro")
    p.add_argument("pdf", type=Path)
    p.add_argument("-o", "--salida", type=Path)
    p.add_argument("--idioma", default="es")
    # Rango de páginas 1-based e inclusivo; sin --hasta se llega hasta la última.
    p.add_argument("--desde", type=int, default=1)
    p.add_argument("--hasta", type=int)
    # Un MP3 por página (útil cuando cada página es un capítulo).
    p.add_argument("--por-pagina", action="store_true")
    # Voz más lenta de gTTS (útil para aprender idiomas).
    p.add_argument("--lento", action="store_true")
    a = p.parse_args(argv)
    conv = Convertidor(motor or MotorGTTS(a.lento), a.idioma)
    # Por defecto el MP3 se llama como el PDF: libro.pdf → libro.mp3.
    salida = a.salida or a.pdf.with_suffix(".mp3")
    try:
        for r in conv.pdf_a_mp3(a.pdf, salida, a.desde, a.hasta, a.por_pagina):
            print(f"Generado: {r}")
        return 0
    # Rango inválido, PDF cifrado o sin texto, archivo inexistente → exit 1.
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def main() -> None:
    sys.exit(ejecutar())
