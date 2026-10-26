"""CLI.

Ejemplos::

    python -m buscador indexar docs/ --indice indice.json
    python -m buscador buscar 'python +bases "base de datos" -oracle' --indice indice.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .indice import Indice


def main(argv: list[str] | None = None) -> int:
    """CLI con dos subcomandos: 'indexar CARPETA' (incremental: reusa el índice existente y
    solo procesa lo que cambió) y 'buscar CONSULTA' (muestra título, puntuación y
    fragmento). Sin índice o con carpeta inválida devuelve 1 con un mensaje claro.
    """
    ap = argparse.ArgumentParser(prog="buscador")
    ap.add_argument("--indice", default="indice.json", type=Path)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("indexar")
    s.add_argument("carpeta", type=Path)
    s = sub.add_parser("buscar")
    s.add_argument("consulta")
    s.add_argument("-n", type=int, default=10)
    a = ap.parse_args(argv)

    if a.cmd == "indexar":
        if not a.carpeta.is_dir():
            print(f"error: no es una carpeta: {a.carpeta}", file=sys.stderr)
            return 1
        ind = Indice.cargar(a.indice) if a.indice.exists() else Indice()
        stats = ind.indexar_carpeta(a.carpeta)
        ind.guardar(a.indice)
        print(f"{len(ind.docs)} documentos, {len(ind.postings)} términos · " +
              ", ".join(f"{k}: {v}" for k, v in stats.items()))
        return 0

    if not a.indice.exists():
        print("error: no hay índice; ejecutá 'indexar' primero", file=sys.stderr)
        return 1
    res = Indice.cargar(a.indice).buscar(a.consulta, a.n)
    if not res:
        print("Sin resultados.")
    for i, r in enumerate(res, 1):
        print(f"{i}. {r.titulo}  ({r.doc_id}, {r.puntuacion:.2f})\n   {r.fragmento}")
    return 0
