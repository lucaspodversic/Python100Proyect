"""CLI: genpass [-l LARGO] [-n CANTIDAD] [--sin-simbolos] [--frase N]."""
from __future__ import annotations

import argparse
import sys
from typing import Sequence

from .nucleo import PALABRAS, Opciones, entropia_bits, fortaleza, generar, generar_frase


def ejecutar(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="genpass")
    # 16 caracteres por defecto: con ~86 símbolos posibles da más de 100 bits de entropía.
    p.add_argument("-l", "--largo", type=int, default=16)
    p.add_argument("-n", "--cantidad", type=int, default=1)
    # Las clases se activan por defecto y se desactivan con --sin-*: lo seguro es lo que no requiere flags.
    p.add_argument("--sin-minusculas", action="store_true")
    p.add_argument("--sin-mayusculas", action="store_true")
    p.add_argument("--sin-digitos", action="store_true")
    p.add_argument("--sin-simbolos", action="store_true")
    p.add_argument("--sin-ambiguos", action="store_true")
    p.add_argument("--frase", type=int, metavar="PALABRAS", help="Generar frase de contraseña")
    p.add_argument("--entropia", action="store_true", help="Mostrar entropía estimada")
    a = p.parse_args(argv)
    try:
        # Se generan `cantidad` contraseñas independientes, una por línea.
        for _ in range(a.cantidad):
            if a.frase:
                # Frase: la entropía depende de la cantidad de palabras y del tamaño de la lista.
                s = generar_frase(a.frase)
                bits = entropia_bits(a.frase, len(PALABRAS))
            else:
                # Los flags --sin-X se invierten para obtener las opciones positivas del dataclass.
                op = Opciones(a.largo, not a.sin_minusculas, not a.sin_mayusculas, not a.sin_digitos,
                              not a.sin_simbolos, a.sin_ambiguos)
                s = generar(op)
                # Tamaño real del alfabeto (ya sin ambiguos si se pidió).
                bits = entropia_bits(a.largo, len("".join(op.clases())))
            # Con --entropia se agrega la estimación separada por tabulador; si no, sólo la contraseña.
            print(f"{s}\t{bits:.0f} bits ({fortaleza(bits)})" if a.entropia else s)
    # Opciones imposibles (largo menor que las clases, ninguna clase, 0 palabras) → exit 1.
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


def main() -> None:
    sys.exit(ejecutar())
