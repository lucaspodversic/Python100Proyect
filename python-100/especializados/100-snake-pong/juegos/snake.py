"""Lógica de Snake en una grilla, por *ticks* discretos.

Reglas:

* La serpiente avanza una celda por tick en la dirección actual.
* No puede girar 180° (si va a la derecha, "izquierda" se ignora): si no, se
  chocaría consigo misma de inmediato.
* Los giros se **encolan** (máx. 2): si el jugador aprieta arriba y luego
  izquierda en el mismo tick, ambos giros se aplican en ticks sucesivos en vez
  de perder el primero. Es lo que hace que el control se sienta "justo".
* Comer agranda la serpiente 1 celda y suma puntos; la comida reaparece en una
  celda libre elegida con un ``random.Random`` propio (semilla → partida reproducible).
* Choque con pared (o con su cuerpo) termina la partida. Con ``paredes=False``
  el tablero es un toro (sale por un borde y entra por el opuesto).
* Si la serpiente llena todo el tablero, se gana.
"""
from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field
from enum import Enum

Celda = tuple[int, int]  # (x, y); y crece hacia abajo, como en pantalla


class Dir(Enum):
    ARRIBA = (0, -1)
    ABAJO = (0, 1)
    IZQUIERDA = (-1, 0)
    DERECHA = (1, 0)

    def opuesta(self) -> "Dir":
        dx, dy = self.value
        return Dir((-dx, -dy))


class Evento(Enum):
    NADA = "nada"
    COMIO = "comio"
    CHOCO = "choco"
    GANO = "gano"


@dataclass
class Snake:
    ancho: int = 20
    alto: int = 15
    paredes: bool = True
    semilla: int | None = None
    cuerpo: deque[Celda] = field(init=False)      # cuerpo[0] es la cabeza
    direccion: Dir = field(init=False, default=Dir.DERECHA)
    comida: Celda | None = field(init=False, default=None)
    puntos: int = field(init=False, default=0)
    vivo: bool = field(init=False, default=True)
    gano: bool = field(init=False, default=False)
    _cola_giros: deque[Dir] = field(init=False)
    _crecer: int = field(init=False, default=0)   # celdas pendientes de crecimiento

    def __post_init__(self) -> None:
        if self.ancho < 5 or self.alto < 3:
            raise ValueError("tablero demasiado chico (mínimo 5x3)")
        self.rng = random.Random(self.semilla)
        cx, cy = self.ancho // 2, self.alto // 2
        # Empieza con 3 celdas horizontales mirando a la derecha.
        self.cuerpo = deque([(cx, cy), (cx - 1, cy), (cx - 2, cy)])
        self._cola_giros = deque(maxlen=2)
        self.colocar_comida()

    @property
    def cabeza(self) -> Celda:
        return self.cuerpo[0]

    def libres(self) -> list[Celda]:
        ocupadas = set(self.cuerpo)
        return [(x, y) for y in range(self.alto) for x in range(self.ancho) if (x, y) not in ocupadas]

    def colocar_comida(self) -> None:
        libres = self.libres()
        # Elegir de la lista de libres (no "reintentar al azar") termina siempre, incluso casi lleno.
        self.comida = self.rng.choice(libres) if libres else None

    def girar(self, d: Dir) -> None:
        """Encola un giro si es válido respecto de la última dirección encolada (o la actual)."""
        ultima = self._cola_giros[-1] if self._cola_giros else self.direccion
        if d not in (ultima, ultima.opuesta()):
            self._cola_giros.append(d)

    def tick(self) -> Evento:
        if not self.vivo or self.gano:
            return Evento.NADA
        if self._cola_giros:
            self.direccion = self._cola_giros.popleft()
        dx, dy = self.direccion.value
        x, y = self.cabeza[0] + dx, self.cabeza[1] + dy
        if not self.paredes:
            x, y = x % self.ancho, y % self.alto  # módulo = "dar la vuelta"
        elif not (0 <= x < self.ancho and 0 <= y < self.alto):
            self.vivo = False
            return Evento.CHOCO
        nueva = (x, y)
        # La cola se mueve en este mismo tick (salvo que estemos creciendo), así que
        # moverse a la celda que la cola libera NO es choque. Por eso la excluimos.
        cuerpo_que_queda = list(self.cuerpo)[:-1] if self._crecer == 0 else list(self.cuerpo)
        if nueva in cuerpo_que_queda:
            self.vivo = False
            return Evento.CHOCO
        self.cuerpo.appendleft(nueva)
        if self._crecer:
            self._crecer -= 1
        else:
            self.cuerpo.pop()
        if nueva == self.comida:
            self.puntos += 10
            self._crecer += 1   # crece en el próximo tick (la cola no se mueve)
            if len(self.cuerpo) + self._crecer >= self.ancho * self.alto:
                self.gano = True
                return Evento.GANO
            self.colocar_comida()
            return Evento.COMIO
        return Evento.NADA

    def velocidad(self, base: float = 8.0) -> float:
        """Ticks por segundo: acelera 0.5 por cada comida, con tope de 20."""
        return min(20.0, base + 0.5 * self.puntos / 10)
