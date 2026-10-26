"""CLI::

    deteccion-fraude comparar
    deteccion-fraude entrenar --salida detector.joblib [--criterio recall --recall-min 0.85]
    deteccion-fraude puntuar --modelo detector.joblib transacciones.csv --salida puntuadas.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .datos import generar_transacciones
from .modelo import DetectorFraude, comparar, dividir


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="deteccion-fraude")
    sub = ap.add_subparsers(dest="cmd", required=True)
    # comparar: tabla baseline vs. modelos con umbral 0.5 y con umbral optimizado.
    c = sub.add_parser("comparar")
    c.add_argument("--n", type=int, default=30000)
    # entrenar: elige umbral por costo (por defecto) o por recall mínimo, y guarda el detector.
    e = sub.add_parser("entrenar")
    e.add_argument("--salida", type=Path, default=Path("detector.joblib"))
    e.add_argument("--n", type=int, default=30000)
    e.add_argument("--tipo", default="boosting", choices=["boosting", "logistica"])
    e.add_argument("--criterio", default="costo", choices=["costo", "recall"])
    e.add_argument("--recall-min", type=float, default=0.8)
    # puntuar: aplica un detector guardado a un CSV nuevo (sin columna fraude).
    p = sub.add_parser("puntuar")
    p.add_argument("--modelo", type=Path, required=True)
    p.add_argument("csv", type=Path)
    p.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args(argv)

    if a.cmd == "comparar":
        print(comparar(generar_transacciones(a.n)).round(3).to_string())
    elif a.cmd == "entrenar":
        # 60/20/20: el umbral se elige con val y el resultado se informa sobre test (nunca visto).
        train, val, test = dividir(generar_transacciones(a.n))
        d = DetectorFraude(a.tipo).entrenar(train, val, a.criterio, a.recall_min)
        r = d.evaluar(test)
        print(f"Umbral elegido: {d.umbral:.3f} | PR-AUC {r['pr_auc']:.3f} | precisión {r['precision']:.2f} "
              f"| recall {r['recall']:.2f} | costo test ${r['costo']:,.0f}")
        d.guardar(a.salida)
    else:
        d = DetectorFraude.cargar(a.modelo)
        df = pd.read_csv(a.csv)
        df["prob_fraude"] = d.probabilidad(df).round(4)
        # Se usa el umbral guardado con el modelo, no 0.5; salida ordenada de más a menos sospechosa.
        df["alerta"] = (df["prob_fraude"] >= d.umbral).astype(int)
        df.sort_values("prob_fraude", ascending=False).to_csv(a.salida, index=False)
        print(f"{int(df['alerta'].sum())} alertas de {len(df)} transacciones → {a.salida}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
