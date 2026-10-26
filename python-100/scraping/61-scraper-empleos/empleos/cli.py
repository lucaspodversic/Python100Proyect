"""CLI. No hay sitio por defecto: hay que indicar --url explícitamente.

Antes de usarlo con un sitio real, verificá que sus términos lo permitan.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .cliente import BloqueadoPorRobots, ClienteEducado, ErrorHTTP
from .parser import PerfilSelectores
from .pipeline import Filtro, ejecutar_pipeline, exportar


# `cliente` inyectable: los tests lo apuntan a un servidor local en 127.0.0.1.
def ejecutar(argv: Sequence[str] | None = None, cliente: ClienteEducado | None = None) -> int:
    p = argparse.ArgumentParser(prog="empleos", description="Scraper genérico de ofertas (respeta robots.txt).")
    # Obligatoria a propósito: el programa no trae ningún sitio "de fábrica".
    p.add_argument("--url", required=True, help="página de listado de un sitio que permita scraping")
    p.add_argument("--perfil", type=Path, help="JSON con selectores CSS (si no hay JSON-LD)")
    # -k y --excluir se pueden repetir (todas las -k deben aparecer).
    p.add_argument("-k", "--palabra", action="append", default=[])
    p.add_argument("--excluir", action="append", default=[])
    p.add_argument("--ubicacion", default="")
    p.add_argument("--remoto", action="store_true")
    p.add_argument("--salario-min", type=float)
    # Tope de páginas a recorrer siguiendo el enlace "siguiente".
    p.add_argument("--paginas", type=int, default=5)
    # Segundos mínimos entre pedidos al mismo host (se respeta un Crawl-delay mayor).
    p.add_argument("--intervalo", type=float, default=2.0)
    p.add_argument("-o", "--salida", type=Path, default=Path("ofertas.csv"))
    a = p.parse_args(argv)
    cliente = cliente or ClienteEducado(intervalo=a.intervalo)
    # Sin perfil sólo se usa JSON-LD.
    perfil = PerfilSelectores.desde_json(a.perfil) if a.perfil else None
    try:
        ofertas = ejecutar_pipeline(cliente, a.url, perfil,
                                    Filtro(tuple(a.palabra), tuple(a.excluir), a.ubicacion, a.remoto, a.salario_min),
                                    a.paginas)
    # Código 3 distinto para "prohibido por robots.txt": no es un fallo técnico.
    except BloqueadoPorRobots as exc:
        print(f"robots.txt no permite {exc}; no se descargó nada.", file=sys.stderr); return 3
    # HTTP 4xx/5xx, URL no soportada, problemas de red o de archivo → exit 1.
    except (ErrorHTTP, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr); return 1
    exportar(ofertas, a.salida)
    print(f"{len(ofertas)} ofertas → {a.salida}")
    return 0


def main() -> None:
    sys.exit(ejecutar())
