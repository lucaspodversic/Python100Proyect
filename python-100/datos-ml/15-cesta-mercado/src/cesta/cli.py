"""CLI::

    cesta ventas.csv [--soporte 0.02] [--confianza 0.4] [--top 15] [--salida reglas.csv]
    cesta --demo
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .apriori import apriori, generar_reglas
from .datos import cargar_tickets, generar_tickets
from .sugerencias import sugerencias_layout


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cesta", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", type=Path, nargs="?", help="columnas: ticket,producto")
    # Soporte 2% y confianza 40%: valores típicos para un supermercado con miles de tickets.
    ap.add_argument("--soporte", type=float, default=0.02)
    ap.add_argument("--confianza", type=float, default=0.4)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--salida", type=Path)
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args(argv)
    if not a.demo and a.csv is None:
        ap.error("indicá un CSV o --demo")
    tickets = generar_tickets() if a.demo else cargar_tickets(a.csv)
    frec = apriori(tickets, a.soporte)
    # lift_min=1: sólo asociaciones positivas (comprar A aumenta la probabilidad de B).
    reglas = generar_reglas(frec, a.confianza, lift_min=1.0)
    print(f"{len(tickets)} tickets, {len(frec)} conjuntos frecuentes, {len(reglas)} reglas\n")
    for r in reglas[: a.top]:
        print(" ", r)
    print("\nSugerencias:")
    for s in sugerencias_layout(reglas):
        print("  •", s)
    if a.salida:
        # Los conjuntos se exportan como texto "a, b" (ordenado) para abrir el CSV en una planilla.
        pd.DataFrame([{"antecedente": ", ".join(sorted(r.antecedente)), "consecuente": ", ".join(sorted(r.consecuente)),
                       "soporte": r.soporte, "confianza": r.confianza, "lift": r.lift, "leverage": r.leverage,
                       "conviction": r.conviction} for r in reglas]).to_csv(a.salida, index=False)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
