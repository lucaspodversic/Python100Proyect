"""Composición procedural basada en reglas.

1. **Progresión armónica**: cadena de Markov sobre funciones tonales.

   * Tónica (I, vi) → Subdominante (ii, IV) → Dominante (V, vii°) → Tónica.
   * Empieza en I; el penúltimo compás es V y el último es I (cadencia
     auténtica).

2. **Melodía**, compás a compás, sobre un patrón rítmico que suma 4 tiempos:

   * en tiempos fuertes (1 y 3) se usa una nota del acorde;
   * en el resto, sobre todo movimiento por grado conjunto (±1 o ±2 grados) y
     a veces saltos;
   * tras un salto grande se compensa en dirección contraria (regla clásica de
     conducción melódica);
   * la melodía se mantiene en un registro cantable y termina en la tónica.

3. **Bajo**: la fundamental del acorde, en redondas o en un patrón de corcheas.

Todo depende de un ``random.Random(semilla)``: la misma semilla produce la
misma pieza.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .teoria import Escala, tonica_midi

# Grado (0-based) → posibles siguientes, con pesos. 0=I 1=ii 2=iii 3=IV 4=V 5=vi 6=vii°
TRANSICIONES: dict[int, dict[int, int]] = {
    0: {3: 4, 4: 3, 5: 3, 1: 2},
    1: {4: 5, 6: 1},
    2: {5: 3, 3: 2},
    3: {4: 4, 1: 2, 0: 2},
    4: {0: 5, 5: 2},
    5: {1: 3, 3: 3},
    6: {0: 1},
}
RITMOS: list[tuple[float, ...]] = [   # en tiempos (negra = 1); cada patrón suma 4
    (1, 1, 1, 1), (2, 1, 1), (1, 1, 2), (1.5, 0.5, 1, 1), (0.5, 0.5, 1, 0.5, 0.5, 1), (2, 2), (1, 0.5, 0.5, 2),
]
RANGO_MELODIA = (60, 84)   # C4–C6
TIEMPOS_FUERTES = (0.0, 2.0)


@dataclass(frozen=True)
class Nota:
    """Una nota: altura MIDI (60 = C4), inicio y duración en tiempos (negras) y velocidad MIDI
    1-127.
    """
    altura: int        # MIDI
    inicio: float      # en tiempos desde el comienzo
    duracion: float    # en tiempos
    velocidad: int = 90


@dataclass
class Pieza:
    """Resultado de la composición: tonalidad, tempo, progresión (un grado por compás de 4/4) y
    tres pistas: melodía, acordes y bajo.
    """
    tonica: str
    modo: str
    tempo: int
    progresion: list[int]
    melodia: list[Nota] = field(default_factory=list)
    bajo: list[Nota] = field(default_factory=list)
    acordes: list[Nota] = field(default_factory=list)

    @property
    def tiempos(self) -> float:
        """Duración en tiempos: 4 por compás."""
        return 4.0 * len(self.progresion)

    @property
    def segundos(self) -> float:
        """Duración en segundos: tiempos × 60 / bpm (p. ej. 4 compases a 120 bpm = 16 × 0.5 = 8
        s).
        """
        return self.tiempos * 60 / self.tempo

    def pistas(self) -> list[list[Nota]]:
        """Las tres pistas en el orden en que se exportan a MIDI (melodía en el canal 0)."""
        return [self.melodia, self.acordes, self.bajo]


def progresion(rng: random.Random, compases: int) -> list[int]:
    """Grados de la progresión: empieza en I y termina con la cadencia V → I."""
    if not 3 <= compases <= 256:
        raise ValueError("compases fuera de rango (3–256)")
    prog = [0]
    while len(prog) < compases - 2:
        opciones = TRANSICIONES[prog[-1]]
        prog.append(rng.choices(list(opciones), weights=list(opciones.values()))[0])
    return prog + [4, 0]  # cadencia auténtica


class Compositor:
    """Compositor procedural con reglas de teoría musical simples: progresión con cadencia V–I,
    melodía en la escala, notas del acorde en los tiempos fuertes, preferencia por
    movimiento por grado conjunto y final en la tónica. Con la misma semilla produce
    siempre la misma pieza.
    """
    def __init__(self, tonica: str = "C", modo: str = "mayor", tempo: int = 100, semilla: int | None = None) -> None:
        """Valida el tempo (40-240 bpm), arma la escala y crea un generador aleatorio propio
        (no el global) para que la semilla dé resultados reproducibles.
        """
        if not 40 <= tempo <= 240:
            raise ValueError("tempo fuera de rango (40–240)")
        self.tonica, self.modo, self.tempo = tonica, modo, tempo
        self.escala = Escala(tonica_midi(tonica, 4), modo)
        self.rng = random.Random(semilla)

    def _acorde_grado(self, g: int) -> int:
        """En pentatónica (5 notas) los grados 0-6 se mapean a la escala mayor de referencia."""
        return g if len(self.escala.intervalos) == 7 else g % len(self.escala.intervalos)

    def componer(self, compases: int = 8) -> Pieza:
        """Compás por compás: elige un ritmo (redonda en el último compás, para cerrar en la
        tónica más cercana). En los tiempos fuertes (0 y 2) va la nota del acorde más
        cercana (30 % de las veces, otra de las 3 más cercanas, para variar). En los
        débiles se mueve por la escala con pasos de ±1 grado como los más probables;
        después de un salto de 3 grados o más, compensa con un paso en sentido contrario.
        Acompañamiento: tríada en redondas y bajo dos octavas abajo, en redonda o con el
        patrón fundamental-quinta-octava-quinta.
        """
        prog = progresion(self.rng, compases)
        pieza = Pieza(self.tonica, self.modo, self.tempo, prog)
        notas_mel = self.escala.notas_en_rango(*RANGO_MELODIA)
        actual = self.escala.tonica + 12  # empieza en la tónica aguda (C5 en Do)
        salto_previo = 0
        for c, grado in enumerate(prog):
            g = self._acorde_grado(grado)
            clases = self.escala.clases_acorde(g)
            t0 = 4.0 * c
            ultimo = c == len(prog) - 1
            ritmo = (4.0,) if ultimo else self.rng.choice(RITMOS)
            t = 0.0
            for dur in ritmo:
                if ultimo:
                    # Final: la tónica más cercana a la nota actual.
                    destino = min((n for n in notas_mel if (n - self.escala.tonica) % 12 == 0),
                                  key=lambda n: abs(n - actual))
                elif t in TIEMPOS_FUERTES:
                    candidatas = [n for n in notas_mel if n % 12 in clases]
                    destino = min(candidatas, key=lambda n: (abs(n - actual), self.rng.random()))
                    if self.rng.random() < 0.3:  # a veces, otra nota del acorde cercana (salto)
                        cercanas = sorted(candidatas, key=lambda n: abs(n - actual))[:3]
                        destino = self.rng.choice(cercanas)
                else:
                    idx = notas_mel.index(actual)
                    if abs(salto_previo) >= 3:
                        paso = -1 if salto_previo > 0 else 1     # compensación tras un salto
                    else:
                        paso = self.rng.choices([-2, -1, 1, 2, 0], weights=[1, 4, 4, 1, 1])[0]
                    destino = notas_mel[max(0, min(len(notas_mel) - 1, idx + paso))]
                salto_previo = notas_mel.index(destino) - notas_mel.index(actual)
                actual = destino
                pieza.melodia.append(Nota(destino, t0 + t, dur, 100 if t in TIEMPOS_FUERTES else 80))
                t += dur
            # Acompañamiento: tríada en la octava 4 (redonda) y bajo dos octavas abajo.
            for n in self.escala.acorde(g):
                pieza.acordes.append(Nota(n, t0, 4.0, 55))
            raiz = self.escala.acorde(g)[0] - 24
            if ultimo or self.rng.random() < 0.5:
                pieza.bajo.append(Nota(raiz, t0, 4.0, 85))
            else:
                for k, n in enumerate((raiz, raiz + 7, raiz + 12, raiz + 7)):  # fundamental-quinta-octava
                    pieza.bajo.append(Nota(n, t0 + k, 1.0, 80))
        return pieza
