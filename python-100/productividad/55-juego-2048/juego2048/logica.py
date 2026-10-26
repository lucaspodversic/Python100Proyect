"""Lógica pura del 2048.

Idea clave: sólo se implementa el movimiento de UNA fila hacia la
izquierda (`mover_fila`). Las otras direcciones se obtienen invirtiendo
filas (derecha) o trasponiendo el tablero (arriba/abajo).

El generador aleatorio se inyecta (`random.Random`) para que los tests
sean deterministas.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum

Tablero = list[list[int]]  # 0 = casilla vacía


# El valor de cada miembro es su tecla WASD: Direccion("a") → IZQUIERDA.
class Direccion(Enum):
    IZQUIERDA = "a"
    DERECHA = "d"
    ARRIBA = "w"
    ABAJO = "s"


def mover_fila(fila: list[int]) -> tuple[list[int], int]:
    """Desliza y fusiona hacia la izquierda. Devuelve (fila nueva, puntos).

    Cada ficha se fusiona como máximo una vez por jugada:
    [2,2,2,2] → [4,4,0,0] (no [8,0,0,0]).
    """
    # Paso 1: deslizar = quitar los ceros (las fichas quedan juntas a la izquierda).
    valores = [v for v in fila if v]
    resultado: list[int] = []
    puntos = 0
    i = 0
    while i < len(valores):
        # Paso 2: dos iguales consecutivas se fusionan y se saltean ambas (cada ficha se fusiona una sola vez).
        if i + 1 < len(valores) and valores[i] == valores[i + 1]:
            resultado.append(valores[i] * 2)
            puntos += valores[i] * 2
            i += 2
        else:
            resultado.append(valores[i])
            i += 1
    # Paso 3: completar con ceros a la derecha hasta el tamaño original.
    return resultado + [0] * (len(fila) - len(resultado)), puntos


def _trasponer(t: Tablero) -> Tablero:
    """Filas ↔ columnas: convierte arriba/abajo en izquierda/derecha."""
    return [list(c) for c in zip(*t)]


def mover_tablero(t: Tablero, d: Direccion) -> tuple[Tablero, int]:
    """Aplica una jugada completa sin modificar el tablero original."""
    # Las columnas se tratan como filas trasponiendo el tablero.
    if d in (Direccion.ARRIBA, Direccion.ABAJO):
        t = _trasponer(t)
    # Hacia la derecha (o abajo, ya traspuesto) = invertir, mover a la izquierda y volver a invertir.
    invertir = d in (Direccion.DERECHA, Direccion.ABAJO)
    # Se construye un tablero nuevo: el original nunca se modifica.
    nuevo, puntos = [], 0
    for fila in t:
        f, p = mover_fila(fila[::-1] if invertir else fila)
        nuevo.append(f[::-1] if invertir else f)
        puntos += p
    if d in (Direccion.ARRIBA, Direccion.ABAJO):
        # Se deshace la trasposición inicial.
        nuevo = _trasponer(nuevo)
    return nuevo, puntos


@dataclass
class Juego:
    """Estado de una partida: tablero, puntaje y RNG inyectable."""
    tamano: int = 4
    rng: random.Random = field(default_factory=random.Random)
    objetivo: int = 2048
    # Se crea en __post_init__ según el tamaño.
    tablero: Tablero = field(init=False)
    puntaje: int = 0

    def __post_init__(self) -> None:
        self.tablero = [[0] * self.tamano for _ in range(self.tamano)]
        # Una partida empieza con dos fichas.
        self.agregar_ficha()
        self.agregar_ficha()

    def vacias(self) -> list[tuple[int, int]]:
        """Coordenadas (fila, columna) de las casillas vacías."""
        return [(r, c) for r in range(self.tamano) for c in range(self.tamano) if not self.tablero[r][c]]

    def agregar_ficha(self) -> bool:
        """Pone un 2 (90 %) o un 4 (10 %) en una casilla vacía al azar."""
        libres = self.vacias()
        # Caso borde: tablero lleno.
        if not libres:
            return False
        r, c = self.rng.choice(libres)
        # Probabilidades del juego original: 90 % un 2, 10 % un 4.
        self.tablero[r][c] = 4 if self.rng.random() < 0.1 else 2
        return True

    def jugar(self, d: Direccion) -> bool:
        """Ejecuta la jugada. Si no cambió nada, no agrega ficha y devuelve False."""
        nuevo, puntos = mover_tablero(self.tablero, d)
        # Regla del juego: una jugada que no mueve nada no cuenta ni agrega ficha.
        if nuevo == self.tablero:
            return False
        self.tablero, self.puntaje = nuevo, self.puntaje + puntos
        self.agregar_ficha()
        return True

    def gano(self) -> bool:
        """True si alguna ficha llegó al objetivo (2048 por defecto)."""
        return any(v >= self.objetivo for fila in self.tablero for v in fila)

    def perdio(self) -> bool:
        """Sin casillas vacías y ninguna jugada cambia el tablero."""
        # Con casillas vacías siempre hay al menos un movimiento posible.
        if self.vacias():
            return False
        # Se perdió si ninguna de las cuatro direcciones cambia el tablero.
        return all(mover_tablero(self.tablero, d)[0] == self.tablero for d in Direccion)
