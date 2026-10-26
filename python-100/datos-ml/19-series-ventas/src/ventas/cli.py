"""CLI::

    series-ventas pronosticar --demo --horizonte 12 --grafico pronostico.png
    series-ventas pronosticar --csv ventas.csv --modelo holt_winters
    series-ventas backtest --demo
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .datos import cargar_csv, generar_ventas
from .evaluacion import backtest
from .graficos import graficar
from .modelos import pronosticar


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="series-ventas")
    sub = ap.add_subparsers(dest="cmd", required=True)
    # Ambos subcomandos comparten la fuente de datos: --demo o --csv, exactamente una (grupo excluyente).
    for nombre in ("pronosticar", "backtest"):
        s = sub.add_parser(nombre)
        g = s.add_mutually_exclusive_group(required=True)
        g.add_argument("--demo", action="store_true")
        g.add_argument("--csv", type=Path)
        # Horizonte por defecto: un año para pronosticar; medio año para backtest (más cortes con 72 meses).
        s.add_argument("--horizonte", type=int, default=12 if nombre == "pronosticar" else 6)
    # --modelo y --grafico sólo tienen sentido al pronosticar; se agregan al subparser ya creado.
    sub.choices["pronosticar"].add_argument("--modelo", default="auto", choices=["auto", "sarima", "holt_winters", "naive"])
    sub.choices["pronosticar"].add_argument("--grafico", type=Path)
    a = ap.parse_args(argv)

    serie = generar_ventas() if a.demo else cargar_csv(a.csv)
    if a.cmd == "pronosticar":
        p = pronosticar(serie, a.horizonte, a.modelo)
        print(f"Modelo usado: {p.modelo}")
        # Las notas explican qué modelos se descartaron y por qué (el fallback nunca es silencioso).
        for n in p.notas:
            print(f"  · {n}")
        print(p.como_tabla().to_string())
        if a.grafico:
            print(f"Gráfico: {graficar(serie, p, a.grafico)}")
    else:
        # Backtest de los tres modelos con métricas promediadas, ordenado por MAE.
        print(backtest(serie, ["sarima", "holt_winters", "naive"], a.horizonte).round(3).to_string())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
