"""Tests de la lógica pura con RNG sembrado."""
import random

import pytest

from juego2048 import Direccion, Juego, mover_fila, mover_tablero
from juego2048.consola import dibujar, jugar


# Fusión simple, doble, con huecos, sin fusiones, sólo deslizar y fusión única por jugada.
@pytest.mark.parametrize("fila,esp,pts", [
    ([2, 2, 0, 0], [4, 0, 0, 0], 4),
    ([2, 2, 2, 2], [4, 4, 0, 0], 8),
    ([4, 0, 4, 8], [8, 8, 0, 0], 8),
    ([2, 4, 8, 16], [2, 4, 8, 16], 0),
    ([0, 0, 0, 2], [2, 0, 0, 0], 0),
    ([2, 2, 4, 0], [4, 4, 0, 0], 4),   # el 4 nuevo no se vuelve a fusionar
])
def test_mover_fila(fila, esp, pts):
    assert mover_fila(fila) == (esp, pts)


# Derecha, arriba (traspuesto) y abajo (traspuesto e invertido) sin mutar el original.
def test_direcciones():
    t = [[2, 0, 0, 2], [0, 0, 0, 0], [2, 0, 0, 0], [0, 0, 0, 0]]
    assert mover_tablero(t, Direccion.DERECHA)[0][0] == [0, 0, 0, 4]
    arriba, pts = mover_tablero(t, Direccion.ARRIBA)
    assert arriba[0] == [4, 0, 0, 2] and pts == 4
    abajo = mover_tablero(t, Direccion.ABAJO)[0]
    assert abajo[3] == [4, 0, 0, 2]
    assert t[0] == [2, 0, 0, 2]  # el original no se modifica


# Misma semilla → mismo tablero inicial con 2 fichas (14 vacías de 16).
def test_juego_inicial_determinista():
    a, b = Juego(rng=random.Random(1)), Juego(rng=random.Random(1))
    assert a.tablero == b.tablero and len(a.vacias()) == 14


# Una ficha ya pegada a la izquierda no se mueve; a la derecha sí y aparece una ficha nueva.
def test_jugada_sin_cambio_no_agrega_ficha():
    j = Juego(rng=random.Random(0))
    j.tablero = [[2, 0, 0, 0], [0] * 4, [0] * 4, [0] * 4]
    assert j.jugar(Direccion.IZQUIERDA) is False
    assert j.jugar(Direccion.DERECHA) is True and len(j.vacias()) == 14


# Tablero en damero sin fusiones posibles → perdió; dos 2048 vecinos se pueden fusionar → no perdió.
def test_ganar_y_perder():
    j = Juego(rng=random.Random(0))
    j.tablero = [[2, 4, 2, 4], [4, 2, 4, 2], [2, 4, 2, 4], [4, 2, 4, 2]]
    assert j.perdio() and not j.gano()
    j.tablero[0][0] = 2048
    assert j.gano()
    j.tablero[0][1] = 2048  # ahora hay fusión posible
    assert not j.perdio()


# Tecla inválida, las cuatro direcciones y "q" para salir, con entrada y salida falsas.
def test_consola():
    teclas = iter(["x", "a", "d", "w", "s", "q"])
    salida = []
    puntaje = jugar(lambda _: next(teclas), salida.append, random.Random(3))
    assert puntaje >= 0 and "Tecla inválida." in salida and salida[0].startswith("Puntaje: 0")
    assert "|" in dibujar(Juego(rng=random.Random(1)))
