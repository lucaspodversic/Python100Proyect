"""CLI: propinas 1234,50 -p 15 -n 3 [--impuesto 21] [--redondear 10]"""
from __future__ import annotations

import argparse
import sys
from typing import Sequence

from .calculo import Cuenta, a_decimal, calcular


def formato(d) -> str:
    """$1.234,50 (formato rioplatense: punto de miles, coma decimal)."""
    # Formato inglés "1,234.50" e intercambio de separadores usando "X" como comodín temporal.
    return "$" + f"{d:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def ejecutar(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="propinas")
    # Los montos se leen como texto y se convierten con a_decimal (acepta coma decimal).
    p.add_argument("subtotal")
    p.add_argument("-p", "--porcentaje", default="10")
    p.add_argument("-n", "--personas", type=int, default=1)
    # "%%" porque argparse interpreta "%" en los textos de ayuda.
    p.add_argument("--impuesto", default="0", help="%% de impuesto a agregar")
    p.add_argument("--sobre-impuesto", action="store_true", help="calcular la propina incluyendo el impuesto")
    p.add_argument("--redondear", help="redondear el total hacia arriba a este múltiplo (p. ej. 100)")
    a = p.parse_args(argv)
    try:
        r = calcular(Cuenta(a_decimal(a.subtotal, "subtotal"), a_decimal(a.porcentaje, "porcentaje"),
                            a.personas, a_decimal(a.impuesto, "impuesto"), a.sobre_impuesto,
                            a_decimal(a.redondear, "redondeo") if a.redondear else None))
    # Números inválidos o fuera de rango → mensaje claro y exit 1.
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    # La línea de impuesto sólo se muestra si hay impuesto.
    if r.impuesto:
        print(f"Impuesto:   {formato(r.impuesto)}")
    print(f"Propina:    {formato(r.propina)} ({r.porcentaje_efectivo}%)")
    print(f"Total:      {formato(r.total)}")
    if a.personas > 1:
        # Resume el reparto como "2×$36,67 / 1×$36,66" en vez de listar a cada persona.
        partes = sorted(set(r.por_persona), reverse=True)
        detalle = " / ".join(f"{r.por_persona.count(x)}×{formato(x)}" for x in partes)
        print(f"Por persona: {detalle}")
    return 0


def main() -> None:
    sys.exit(ejecutar())
