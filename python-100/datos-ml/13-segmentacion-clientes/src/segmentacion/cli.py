"""CLI::

    segmentacion transacciones.csv [--k auto|4] [--salida segmentos.csv]
    segmentacion --demo
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .clustering import Segmentador, elegir_k
from .datos import generar_transacciones
from .rfm import calcular_rfm


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="segmentacion", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    # nargs="?": el CSV es opcional porque --demo no lo necesita; la validación se hace abajo.
    ap.add_argument("csv", type=Path, nargs="?", help="columnas: cliente,fecha,monto")
    # --k es texto: "auto" (elegir por silueta) o un número entero.
    ap.add_argument("--k", default="auto")
    ap.add_argument("--salida", type=Path)
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args(argv)
    if not a.demo and a.csv is None:
        # ap.error imprime el uso y sale con código 2, como cualquier error de argparse.
        ap.error("indicá un CSV o --demo")
    # generar_transacciones devuelve (tx, perfiles); en la demo sólo se usan las transacciones.
    tx = generar_transacciones()[0] if a.demo else pd.read_csv(a.csv)
    rfm = calcular_rfm(tx)
    if a.k == "auto":
        k, puntajes = elegir_k(rfm)
        print("Silueta por k: " + ", ".join(f"{kk}={v:.2f}" for kk, v in puntajes.items()) + f" → k={k}")
    else:
        k = int(a.k)
    res = Segmentador(k).ajustar(rfm)
    # to_string() muestra la tabla completa sin que pandas la recorte con "...".
    print(Segmentador.resumen(res).round(1).to_string())
    if a.salida:
        res.to_csv(a.salida)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
