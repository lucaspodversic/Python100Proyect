"""Interfaz de consola con E/S y azar inyectables."""
from __future__ import annotations

import argparse
import random
import sys
from typing import Callable, Sequence

from .logica import Partida, Resultado
from .palabras import PALABRAS

# Texto que se muestra según el resultado de cada intento.
MENSAJES = {Resultado.ACIERTO: "¡Bien!", Resultado.FALLO: "No está.",
            Resultado.REPETIDA: "Ya probaste esa letra.", Resultado.INVALIDA: "Escribí una letra."}


def jugar(palabra: str, leer: Callable[[str], str] = input, escribir: Callable[[str], None] = print) -> bool:
    """Juega una partida completa con E/S inyectable; devuelve True si se ganó."""
    p = Partida(palabra)
    while not p.terminada():
        escribir(p.dibujo())
        # `or '-'`: si todavía no hay letras fallidas se muestra un guion.
        escribir(f"Palabra: {p.mascara()}   Fallidas: {', '.join(p.fallidas()) or '-'}")
        try:
            entrada = leer("Letra o palabra: ")
        # Fin de la entrada (Ctrl+D): se abandona y la partida cuenta como perdida.
        except EOFError:
            break
        escribir(MENSAJES[p.intentar(entrada)])
    # Dibujo antes de cada intento y uno final con el estado definitivo.
    escribir(p.dibujo())
    if p.gano():
        escribir(f"¡Ganaste! La palabra era «{p.palabra}».")
        return True
    escribir(f"Perdiste. La palabra era «{p.palabra}».")
    return False


def ejecutar(argv: Sequence[str] | None = None, rng: random.Random | None = None,
             leer: Callable[[str], str] = input, escribir: Callable[[str], None] = print) -> int:
    """CLI: elige categoría (o una al azar) y palabra; exit 0 si se gana, 1 si se pierde."""
    ap = argparse.ArgumentParser(prog="ahorcado")
    # choices: argparse rechaza solo una categoría inexistente.
    ap.add_argument("-c", "--categoria", choices=sorted(PALABRAS))
    a = ap.parse_args(argv)
    rng = rng or random.Random()
    # sorted(): orden estable de categorías, así la misma semilla siempre elige lo mismo.
    cat = a.categoria or rng.choice(sorted(PALABRAS))
    escribir(f"Categoría: {cat}")
    return 0 if jugar(rng.choice(PALABRAS[cat]), leer, escribir) else 1


def main() -> None:
    sys.exit(ejecutar())
