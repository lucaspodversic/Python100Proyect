"""CLI: autodoc CARPETA_O_ARCHIVO [-f md|html] [-o salida]."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .extractor import extraer_modulo, extraer_paquete
from .render import a_html, a_markdown


def ejecutar(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="autodoc")
    # Puede ser una carpeta (paquete completo) o un único archivo .py.
    p.add_argument("origen", type=Path)
    p.add_argument("-f", "--formato", choices=["md", "html"], default="md")
    p.add_argument("-o", "--salida", type=Path)
    p.add_argument("--titulo", default="Documentación")
    # Por defecto sólo se documenta la API pública (nombres sin "_").
    p.add_argument("--privados", action="store_true")
    a = p.parse_args(argv)
    # Carpeta: un Modulo por archivo con nombres con puntos; archivo suelto: se nombra por su stem.
    if a.origen.is_dir():
        mods = extraer_paquete(a.origen, a.privados)
    else:
        mods = [extraer_modulo(a.origen.read_text(encoding="utf-8"), a.origen.stem, a.privados)]
    # Se elige el renderizador según el formato; ambos tienen la misma firma.
    texto = (a_html if a.formato == "html" else a_markdown)(mods, a.titulo)
    if a.salida:
        # Crea carpetas intermedias (p. ej. docs/) si no existen.
        a.salida.parent.mkdir(parents=True, exist_ok=True)
        a.salida.write_text(texto, encoding="utf-8")
        print(f"Documentación escrita en {a.salida}")
    else:
        # Sin -o se escribe a stdout (write evita el salto de línea extra de print).
        sys.stdout.write(texto)
    return 0


def main() -> None:
    sys.exit(ejecutar())
