"""Lógica de Pong en coordenadas continuas (unidades = píxeles lógicos), avance por ``dt``.

Física:

* La pelota se mueve con velocidad ``(vx, vy)``; rebota en el techo/piso
  invirtiendo ``vy`` y "reflejando" la posición para no quedar enterrada.
* Al pegar en una paleta, el ángulo de salida depende de **dónde** pegó:
  en el centro sale recta, en los bordes sale a ±60°. Así el jugador controla
  la dirección (igual que el Pong original). Cada golpe acelera un 5 % hasta
  un tope.
* Si la pelota pasa una paleta, punto para el otro lado y se re-saca hacia
  quien perdió el punto.
* Para evitar el "efecto túnel" (con dt grande la pelota podría atravesar la
  paleta sin tocarla), el avance se divide en subpasos de como mucho 4 px.

La IA es una paleta que persigue la pelota con velocidad máxima limitada
y una zona muerta, así no es perfecta.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum

ANGULO_MAX = math.radians(60)
ACELERACION = 1.05


class EventoPong(Enum):
    REBOTE_PARED = "pared"
    GOLPE = "golpe"
    PUNTO_IZQ = "punto_izq"    # punto para el jugador izquierdo
    PUNTO_DER = "punto_der"
    FIN = "fin"


@dataclass
class Paleta:
    x: float           # borde izquierdo
    y: float           # borde superior
    ancho: float = 10
    alto: float = 70
    velocidad: float = 360   # px/s

    @property
    def centro(self) -> float:
        return self.y + self.alto / 2

    def mover(self, direccion: int, dt: float, alto_campo: float) -> None:
        """direccion ∈ {-1, 0, 1}; queda acotada al campo."""
        self.y = min(max(0.0, self.y + direccion * self.velocidad * dt), alto_campo - self.alto)


@dataclass
class Pelota:
    x: float
    y: float
    vx: float
    vy: float
    radio: float = 6


@dataclass
class Pong:
    ancho: float = 640
    alto: float = 400
    puntos_para_ganar: int = 5
    velocidad_inicial: float = 300
    velocidad_max: float = 900
    semilla: int | None = None
    izq: Paleta = field(init=False)
    der: Paleta = field(init=False)
    pelota: Pelota = field(init=False)
    marcador: list[int] = field(init=False, default_factory=lambda: [0, 0])
    terminado: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.semilla)
        self.izq = Paleta(20, self.alto / 2 - 35)
        self.der = Paleta(self.ancho - 30, self.alto / 2 - 35)
        self.sacar(hacia=self.rng.choice((-1, 1)))

    def sacar(self, hacia: int) -> None:
        """Pelota al centro, hacia ``hacia`` (-1 izquierda, 1 derecha), ángulo aleatorio de ±30°."""
        ang = self.rng.uniform(-math.radians(30), math.radians(30))
        v = self.velocidad_inicial
        self.pelota = Pelota(self.ancho / 2, self.alto / 2, hacia * v * math.cos(ang), v * math.sin(ang))

    def actualizar(self, dt: float, dir_izq: int = 0, dir_der: int = 0) -> list[EventoPong]:
        if self.terminado:
            return []
        self.izq.mover(dir_izq, dt, self.alto)
        self.der.mover(dir_der, dt, self.alto)
        p = self.pelota
        rapidez = math.hypot(p.vx, p.vy)
        pasos = max(1, math.ceil(rapidez * dt / 4))   # subpasos de ≤ 4 px (anti-túnel)
        eventos: list[EventoPong] = []
        for _ in range(pasos):
            ev = self._subpaso(dt / pasos)
            eventos.extend(ev)
            if any(e in (EventoPong.PUNTO_IZQ, EventoPong.PUNTO_DER) for e in ev):
                break   # tras un punto se re-sacó: no seguimos con el dt viejo
        return eventos

    def _subpaso(self, dt: float) -> list[EventoPong]:
        p, ev = self.pelota, []
        p.x += p.vx * dt
        p.y += p.vy * dt
        # Techo y piso: reflejamos posición y velocidad.
        if p.y - p.radio < 0:
            p.y, p.vy = 2 * p.radio - p.y, abs(p.vy)
            ev.append(EventoPong.REBOTE_PARED)
        elif p.y + p.radio > self.alto:
            p.y, p.vy = 2 * (self.alto - p.radio) - p.y, -abs(p.vy)
            ev.append(EventoPong.REBOTE_PARED)
        # Paletas: solo chequeamos la que la pelota tiene enfrente (según el signo de vx).
        if p.vx < 0 and self._toca(self.izq):
            self._golpe(self.izq, +1)
            p.x = self.izq.x + self.izq.ancho + p.radio
            ev.append(EventoPong.GOLPE)
        elif p.vx > 0 and self._toca(self.der):
            self._golpe(self.der, -1)
            p.x = self.der.x - p.radio
            ev.append(EventoPong.GOLPE)
        # Salió del campo → punto.
        if p.x + p.radio < 0:
            ev.append(self._punto(1))
        elif p.x - p.radio > self.ancho:
            ev.append(self._punto(0))
        return ev

    def _toca(self, pal: Paleta) -> bool:
        """Intersección círculo-rectángulo: punto del rectángulo más cercano al centro."""
        p = self.pelota
        cx = min(max(p.x, pal.x), pal.x + pal.ancho)
        cy = min(max(p.y, pal.y), pal.y + pal.alto)
        return (p.x - cx) ** 2 + (p.y - cy) ** 2 <= p.radio ** 2

    def _golpe(self, pal: Paleta, sentido: int) -> None:
        p = self.pelota
        # Posición relativa del impacto en [-1, 1]: -1 borde superior, 1 borde inferior.
        rel = max(-1.0, min(1.0, (p.y - pal.centro) / (pal.alto / 2)))
        ang = rel * ANGULO_MAX
        v = min(self.velocidad_max, math.hypot(p.vx, p.vy) * ACELERACION)
        p.vx, p.vy = sentido * v * math.cos(ang), v * math.sin(ang)

    def _punto(self, jugador: int) -> EventoPong:
        self.marcador[jugador] += 1
        if self.marcador[jugador] >= self.puntos_para_ganar:
            self.terminado = True
        # Re-saque hacia quien perdió el punto (le da la iniciativa de devolver).
        self.sacar(hacia=-1 if jugador == 1 else 1)
        return EventoPong.PUNTO_IZQ if jugador == 0 else EventoPong.PUNTO_DER

    @property
    def ganador(self) -> int | None:
        if not self.terminado:
            return None
        return 0 if self.marcador[0] >= self.puntos_para_ganar else 1


def ia(paleta: Paleta, pelota: Pelota, zona_muerta: float = 10) -> int:
    """Dirección que tomaría una IA simple: seguir la altura de la pelota, sin temblar
    cuando ya está alineada (zona muerta). Su "torpeza" viene de la velocidad máxima de la paleta."""
    diff = pelota.y - paleta.centro
    if abs(diff) <= zona_muerta:
        return 0
    return 1 if diff > 0 else -1
