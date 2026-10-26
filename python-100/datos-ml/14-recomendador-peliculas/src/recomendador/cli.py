"""CLI::

    recomendador evaluar [--csv ratings.csv]
    recomendador recomendar U007 [--csv ratings.csv] [--modelo knn|mf] [-n 5]
    recomendador similares "Terror 03"

El CSV debe tener columnas ``usuario,pelicula,nota`` (MovieLens: renombrar userId/movieId/rating).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .datos import Calificaciones, dividir, generar_calificaciones
from .evaluacion import precision_at_k, rmse
from .modelos import BaselineSesgos, FactorizacionMatricial, ItemKNN, populares, recomendar


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="recomendador", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("accion", choices=["evaluar", "recomendar", "similares"])
    # "objetivo" es el usuario (recomendar) o la película (similares); evaluar no lo usa.
    ap.add_argument("objetivo", nargs="?")
    ap.add_argument("--csv", type=Path)
    ap.add_argument("--modelo", choices=["knn", "mf"], default="knn")
    ap.add_argument("-n", type=int, default=5)
    a = ap.parse_args(argv)
    # Sin CSV se usan calificaciones sintéticas (200 usuarios × 50 películas).
    df = pd.read_csv(a.csv) if a.csv else generar_calificaciones()
    if a.accion == "evaluar":
        train, test = dividir(df)
        # Ejes fijados con TODOS los usuarios/películas: así el índice de cada uno coincide entre train y test.
        c = Calificaciones.desde_df(train, sorted(df["usuario"].unique()), sorted(df["pelicula"].unique()))
        for nombre, m in [("baseline", BaselineSesgos().ajustar(c)), ("item-knn", ItemKNN().ajustar(c)),
                          ("factorización", FactorizacionMatricial(epocas=30).ajustar(c))]:
            # Cada modelo predice la matriz completa y se mide sólo en las celdas del test.
            pred = m.predecir_matriz()
            print(f"{nombre:14s} RMSE={rmse(pred, c, test):.3f}  P@5={precision_at_k(pred, c, test):.2f}")
        return 0
    # Para recomendar se entrena con todos los datos (no hace falta reservar test).
    c = Calificaciones.desde_df(df)
    if a.accion == "similares":
        for p, s in ItemKNN().ajustar(c).similares(a.objetivo, a.n):
            print(f"  {s:+.2f}  {p}")
        return 0
    # Arranque en frío: sin historial no hay filtrado colaborativo posible → populares.
    if a.objetivo not in c.usuarios:
        print("Usuario nuevo: recomendando populares")
        lista = populares(c, a.n)
    else:
        modelo = ItemKNN().ajustar(c) if a.modelo == "knn" else FactorizacionMatricial(epocas=30).ajustar(c)
        lista = recomendar(modelo, c, a.objetivo, a.n)
    for p, s in lista:
        print(f"  {s:.2f}  {p}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
