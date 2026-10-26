"""CLI: wikiextractor "Python (lenguaje de programación)" [--idioma es] [--tablas carpeta] [--json]."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from .api import ApiWikipedia, ErrorHTTP, ErrorWiki
from .extraer import extraer_articulo


# `api` inyectable: los tests pasan una que apunta al servidor local.
def ejecutar(argv: Sequence[str] | None = None, api: ApiWikipedia | None = None) -> int:
    p = argparse.ArgumentParser(prog="wikiextractor")
    p.add_argument("titulo")
    p.add_argument("--idioma", default="es")
    p.add_argument("--buscar", action="store_true", help="buscar títulos en vez de extraer")
    p.add_argument("--tablas", type=Path, help="carpeta donde guardar las tablas como CSV")
    p.add_argument("--json", action="store_true", help="imprimir todo como JSON")
    # Wikimedia pide un contacto real en el User-Agent: el usuario debería poner el suyo.
    p.add_argument("--contacto", default="https://example.org/contacto", help="email/URL para el User-Agent")
    a = p.parse_args(argv)
    try:
        # Dentro del try: un idioma inválido (ValueError) también termina en exit 1.
        api = api or ApiWikipedia(a.idioma, contacto=a.contacto)
        # Modo búsqueda: sólo lista títulos y termina.
        if a.buscar:
            for t in api.buscar(a.titulo):
                print(t)
            return 0
        titulo, html = api.html_articulo(a.titulo)
    # Errores de la API, HTTP, validación o red → mensaje a stderr y exit 1.
    except (ErrorWiki, ErrorHTTP, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    # El parseo es local: ya no hace falta red.
    art = extraer_articulo(titulo, html)
    # --json: el dataclass completo; ensure_ascii=False conserva tildes y eñes.
    if a.json:
        print(json.dumps(asdict(art), ensure_ascii=False, indent=2))
    else:
        print(f"# {art.titulo}\n\n{art.resumen}\n")
        for clave, valor in art.infobox.items():
            print(f"- {clave}: {valor}")
        print("\nSecciones:")
        for nivel, s in art.secciones:
            # h2 sin sangría, h3 con dos espacios.
            print("  " * (nivel - 2) + f"• {s}")
        print(f"\nTablas encontradas: {len(art.tablas)}")
    # Las tablas se guardan como CSV además de cualquier salida elegida.
    if a.tablas:
        for r in art.guardar_tablas(a.tablas):
            print(f"Tabla guardada en {r}")
    return 0


def main() -> None:
    sys.exit(ejecutar())
