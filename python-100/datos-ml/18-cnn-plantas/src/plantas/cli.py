"""CLI::

    cnn-plantas demo                                  # entrena y evalúa con hojas sintéticas
    cnn-plantas entrenar --carpeta PlantVillage/color --salida modelo.pt --lado 64 --epocas 20
    cnn-plantas predecir --modelo modelo.pt hoja.jpg
"""

from __future__ import annotations

import argparse
from pathlib import Path

import torch
from torch.utils.data import random_split

from .datos import CLASES_SINTETICAS, DatasetCarpetas, generar_hojas
from .entrenamiento import Clasificador, dividir


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cnn-plantas")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo")
    # demo no necesita datos externos: genera hojas sintéticas, entrena y muestra la matriz de confusión.
    d.add_argument("--n", type=int, default=120, help="imágenes por clase")
    d.add_argument("--salida", type=Path)
    e = sub.add_parser("entrenar")
    e.add_argument("--carpeta", type=Path, required=True)
    e.add_argument("--salida", type=Path, default=Path("modelo_plantas.pt"))
    e.add_argument("--lado", type=int, default=64)
    e.add_argument("--epocas", type=int, default=20)
    p = sub.add_parser("predecir")
    p.add_argument("--modelo", type=Path, required=True)
    # nargs="+": una o más imágenes a clasificar en la misma corrida.
    p.add_argument("imagenes", type=Path, nargs="+")
    a = ap.parse_args(argv)

    if a.cmd == "demo":
        x, y = generar_hojas(a.n)
        # 75% train / 25% validación con semilla fija.
        tr, va = dividir(x, y)
        c = Clasificador(CLASES_SINTETICAS)
        print(f"Red con {c.red.n_parametros():,} parámetros; {len(tr)} train / {len(va)} val")
        h = c.entrenar(tr, va)
        r = c.evaluar(va)
        # mejor_epoca empieza en 0; se muestra en base 1 para la persona.
        print(f"Exactitud val: {r['exactitud']:.3f} (mejor época {h.mejor_epoca + 1})")
        print("Matriz de confusión (filas = real):", *CLASES_SINTETICAS)
        for nombre, fila in zip(CLASES_SINTETICAS, r["matriz_confusion"]):  # type: ignore[arg-type]
            print(f"  {nombre:13s} {fila}")
        if a.salida:
            c.guardar(a.salida)
    elif a.cmd == "entrenar":  # pragma: no cover - requiere el dataset real
        ds = DatasetCarpetas(a.carpeta, a.lado, aumentar=True)
        # 20% para validación (al menos una imagen); random_split con generador sembrado = partición reproducible.
        n_val = max(1, len(ds) // 5)
        tr, va = random_split(ds, [len(ds) - n_val, n_val], generator=torch.Generator().manual_seed(0))
        # Con datos reales (38 clases, imágenes más grandes) se usa una red más ancha (32 en vez de 16).
        c = Clasificador(ds.clases, ancho=32, lado=a.lado)
        c.entrenar(tr, va, epocas=a.epocas)
        print(f"Exactitud val: {c.evaluar(va)['exactitud']:.3f}")
        c.guardar(a.salida)
    else:
        c = Clasificador.cargar(a.modelo)
        for img in a.imagenes:
            clase, prob = c.predecir_imagen(img)
            print(f"{img.name}: {clase} ({prob:.0%})")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
