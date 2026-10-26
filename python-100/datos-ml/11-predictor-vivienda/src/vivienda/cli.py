"""CLI::

    vivienda entrenar [--csv casas.csv] [--modelo gbr|bosque|ridge] [--salida modelo.joblib] [--comparar]
    vivienda predecir --modelo modelo.joblib --m2 80 --ambientes 3 --banos 1 --antiguedad 20 \
                      --cochera 1 --distancia 0.5 --barrio Norte
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .datos import generar_dataset
from .modelo import MODELOS, Predictor, comparar_modelos


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="vivienda", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("entrenar")
    e.add_argument("--csv", type=Path)
    # choices sale del dict MODELOS: agregar un modelo allí lo habilita automáticamente en la CLI.
    e.add_argument("--modelo", choices=list(MODELOS), default="gbr")
    e.add_argument("--salida", type=Path, default=Path("modelo.joblib"))
    # --comparar imprime el R² por validación cruzada de todos los modelos antes de entrenar el elegido.
    e.add_argument("--comparar", action="store_true")
    p = sub.add_parser("predecir")
    p.add_argument("--modelo", type=Path, default=Path("modelo.joblib"))
    # Un argumento por variable numérica, generado en bucle para no repetir 6 add_argument casi iguales.
    for campo, tipo in [("m2", float), ("ambientes", int), ("banos", int), ("antiguedad", int),
                        ("cochera", int), ("distancia", float)]:
        p.add_argument(f"--{campo}", type=tipo, required=True)
    p.add_argument("--barrio", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "entrenar":
        # Sin CSV se entrena con el dataset sintético (útil para probar la herramienta).
        df = pd.read_csv(a.csv) if a.csv else generar_dataset()
        if a.comparar:
            for n, r2 in comparar_modelos(df).items():
                print(f"  {n:7s} R² CV = {r2:.3f}")
        pred = Predictor(a.modelo)
        m = pred.entrenar(df)
        # MAE: error medio en USD; RMSE penaliza más los errores grandes; MAPE: error relativo; R²: varianza explicada.
        print(f"MAE ${m['mae']:,.0f} | RMSE ${m['rmse']:,.0f} | MAPE {m['mape']:.1%} | R² {m['r2']:.3f}")
        pred.guardar(a.salida)
        print(f"Modelo guardado en {a.salida}")
    else:
        pred = Predictor.cargar(a.modelo)
        # Se arma un registro con los mismos nombres de columna que el entrenamiento ("--distancia" → distancia_subte_km).
        precio = pred.predecir([{"m2": a.m2, "ambientes": a.ambientes, "banos": a.banos, "antiguedad": a.antiguedad,
                                 "cochera": a.cochera, "distancia_subte_km": a.distancia, "barrio": a.barrio}])[0]
        print(f"Precio estimado: USD {precio:,.0f}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
