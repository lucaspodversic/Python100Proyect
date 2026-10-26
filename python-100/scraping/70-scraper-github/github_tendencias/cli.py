"""CLI: github_tendencias [--dias 7] [--lenguaje python] [--tema cli] [--cantidad 25] [--csv f.csv]

El token se lee de la variable GITHUB_TOKEN (opcional; nunca se imprime).
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .api import ApiGitHub, LimiteExcedido
from .cliente import ErrorHTTP
from .ranking import exportar_csv, markdown, ordenar_por_ritmo


def ejecutar(argv: Sequence[str] | None = None, api: ApiGitHub | None = None,
             entorno: Mapping[str, str] = os.environ,
             ahora: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> int:
    """Exit codes: 0 ok, 1 error de red/parámetros, 4 rate limit excedido.

    `api`, `entorno` y `ahora` se inyectan para que los tests no usen red, variables reales ni el reloj.
    """
    p = argparse.ArgumentParser(prog="github_tendencias")
    p.add_argument("--dias", type=int, default=7)
    p.add_argument("--lenguaje"); p.add_argument("--tema")
    p.add_argument("--min-estrellas", type=int)
    p.add_argument("--cantidad", type=int, default=25)
    p.add_argument("--ritmo", action="store_true", help="ordenar por estrellas/día")
    p.add_argument("--csv", type=Path)
    a = p.parse_args(argv)
    # El token sale del entorno (no de argv: quedaría en el historial del shell).
    api = api or ApiGitHub(token=entorno.get("GITHUB_TOKEN"))
    # Un único "ahora" para la consulta y los cálculos de ritmo: resultados coherentes.
    momento = ahora()
    try:
        repos = api.tendencias(a.dias, momento.date(), lenguaje=a.lenguaje, tema=a.tema,
                               min_estrellas=a.min_estrellas, cantidad=a.cantidad)
    except LimiteExcedido as exc:
        # Código propio (4) para que un script pueda esperar y reintentar.
        print(exc, file=sys.stderr); return 4
    except (ErrorHTTP, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr); return 1
    # Por defecto queda el orden de GitHub (estrellas totales); --ritmo reordena.
    if a.ritmo:
        repos = ordenar_por_ritmo(repos, momento)
    print(markdown(repos, momento) if repos else "Sin resultados.")
    if a.csv:
        print(f"CSV: {exportar_csv(repos, a.csv, momento)}")
    return 0


def main() -> None:
    sys.exit(ejecutar())
