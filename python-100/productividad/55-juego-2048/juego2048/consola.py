"""Interfaz de consola: dibuja el tablero y lee WASD (Enter para confirmar)."""
from __future__ import annotations

import random
import sys
from typing import Callable

from .logica import Direccion, Juego


def dibujar(j: Juego) -> str:
    """Devuelve el tablero como texto con bordes y el puntaje arriba."""
    # Ancho de celda según la ficha más grande (mínimo 4) para que las columnas no se desalineen.
    ancho = max(4, len(str(max(max(f) for f in j.tablero))))
    sep = "+" + ("-" * (ancho + 2) + "+") * j.tamano
    lineas = [f"Puntaje: {j.puntaje}", sep]
    for fila in j.tablero:
        # Las casillas vacías (0) se dibujan con "." para leer mejor.
        lineas.append("|" + "|".join(f" {(str(v) if v else '.'):>{ancho}} " for v in fila) + "|")
        lineas.append(sep)
    return "\n".join(lineas)


def jugar(leer: Callable[[str], str] = input, escribir: Callable[[str], None] = print,
          rng: random.Random | None = None) -> int:
    """Bucle principal; devuelve el puntaje final. `leer`/`escribir` inyectables."""
    # Sin RNG explícito el juego es aleatorio de verdad; los tests pasan uno sembrado.
    j = Juego(rng=rng or random.Random())
    # El mensaje de victoria se muestra una sola vez; después se puede seguir jugando.
    aviso_ganador = False
    while True:
        escribir(dibujar(j))
        if j.gano() and not aviso_ganador:
            escribir("¡Llegaste a 2048! Podés seguir jugando.")
            aviso_ganador = True
        # Se chequea antes de pedir tecla: si no hay jugadas posibles, termina.
        if j.perdio():
            escribir("Fin del juego.")
            return j.puntaje
        try:
            tecla = leer("Movimiento (w/a/s/d, q para salir): ").strip().lower()
        # Ctrl+D o fin de la entrada (p. ej. stdin redirigido) equivale a salir.
        except EOFError:
            tecla = "q"
        if tecla == "q":
            return j.puntaje
        try:
            # Direccion("x") lanza ValueError para teclas que no son w/a/s/d.
            if not j.jugar(Direccion(tecla)):
                escribir("Ese movimiento no cambia nada.")
        except ValueError:
            escribir("Tecla inválida.")


def main() -> None:
    """Punto de entrada: juega y muestra el puntaje final."""
    puntos = jugar()
    print(f"Puntaje final: {puntos}")
    sys.exit(0)
