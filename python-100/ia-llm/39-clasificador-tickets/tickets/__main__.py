"""Uso:
  python -m tickets "texto del ticket"
  python -m tickets --evaluar datos.csv     (columnas: texto,categoria)"""
import csv
import json
import sys

from tickets.clasificador import CATEGORIAS, clasificar
from tickets.llm import crear_proveedor
from tickets.metricas import reporte, tabla_matriz


def main(argv: list[str]) -> None:
    prov = crear_proveedor()
    # Sin clave de LLM se usa directo el clasificador por palabras clave.
    llm = None if prov.nombre == "falso" else prov
    if len(argv) == 2 and argv[0] == "--evaluar":
        with open(argv[1], encoding="utf-8") as f:
            filas = list(csv.DictReader(f))
        # Modo evaluación: compara predicción vs. etiqueta real de cada fila.
        pred = [clasificar(f["texto"], llm).categoria for f in filas]
        etiquetas = list(CATEGORIAS)
        r = reporte([f["categoria"] for f in filas], pred, etiquetas)
        print(f"Exactitud: {r['exactitud']}  F1 macro: {r['f1_macro']}\n{tabla_matriz(r['matriz'], etiquetas)}")
    elif argv:
        print(json.dumps(clasificar(" ".join(argv), llm).__dict__, ensure_ascii=False))
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
