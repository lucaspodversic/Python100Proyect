"""CLI::

    sentimiento entrenar [--csv etiquetadas.csv] [--salida modelo.joblib]
    sentimiento clasificar "Llegó roto, un desastre" "Excelente!"
    sentimiento clasificar --archivo reseñas.csv --columna texto --salida resultado.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .corpus import cargar_reseñas_reales, generar_corpus
from .modelo import ClasificadorSentimiento


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sentimiento", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("entrenar")
    e.add_argument("--csv", type=Path, help="CSV con columnas texto,etiqueta")
    e.add_argument("--salida", type=Path, default=Path("sentimiento.joblib"))
    c = sub.add_parser("clasificar")
    # nargs="*": textos sueltos opcionales; se pueden combinar con --archivo.
    c.add_argument("textos", nargs="*")
    c.add_argument("--modelo", type=Path, default=Path("sentimiento.joblib"))
    c.add_argument("--archivo", type=Path)
    c.add_argument("--columna", default="texto")
    c.add_argument("--salida", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "entrenar":
        # Sin CSV propio se entrena con el corpus sintético por plantillas.
        df = pd.read_csv(a.csv) if a.csv else generar_corpus()
        clf = ClasificadorSentimiento().entrenar(df["texto"], df["etiqueta"])
        # Siempre se evalúa contra reseñas escritas a mano (no vistas): mide si generaliza más allá de las plantillas.
        ev = clf.evaluar(cargar_reseñas_reales())
        print(f"Evaluación en reseñas reales: accuracy={ev['accuracy']:.2f} F1-macro={ev['f1_macro']:.2f}")
        print(ev["reporte"])
        clf.guardar(a.salida)
        return 0
    clf = ClasificadorSentimiento.cargar(a.modelo)
    if a.archivo:
        df = pd.read_csv(a.archivo)
        # astype(str): celdas vacías (NaN) o numéricas no rompen el vectorizador.
        res = clf.predecir_con_confianza(df[a.columna].astype(str).tolist())
        # zip(*res) "transpone" [(etiqueta, p), ...] en dos columnas.
        df["sentimiento"], df["confianza"] = zip(*res)
        print(df["sentimiento"].value_counts().to_string())
        if a.salida:
            df.to_csv(a.salida, index=False)
    # Con lista vacía de textos este bucle no hace nada (caso de sólo --archivo).
    for t, (e_, p) in zip(a.textos, clf.predecir_con_confianza(a.textos)):
        print(f"[{e_:8s} {p:.0%}] {t}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
