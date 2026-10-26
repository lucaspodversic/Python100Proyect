"""Teoría musical mínima: notas MIDI, escalas y acordes diatónicos.

* Las notas son números MIDI (60 = Do central, C4) y las frecuencias usan
  temperamento igual: ``f = 440 · 2^((n - 69) / 12)``.
* Una escala es una lista de intervalos en semitonos desde la tónica.
* Los acordes diatónicos se forman apilando terceras dentro de la escala
  (grados 1-3-5).
"""
from __future__ import annotations

NOMBRES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
ALIAS = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#",
         "Do": "C", "Re": "D", "Mi": "E", "Fa": "F", "Sol": "G", "La": "A", "Si": "B"}

ESCALAS: dict[str, tuple[int, ...]] = {
    "mayor": (0, 2, 4, 5, 7, 9, 11),
    "menor": (0, 2, 3, 5, 7, 8, 10),        # menor natural (eólica)
    "dorica": (0, 2, 3, 5, 7, 9, 10),
    "mixolidia": (0, 2, 4, 5, 7, 9, 10),
    "pentatonica": (0, 2, 4, 7, 9),
}


def tonica_midi(nombre: str, octava: int = 4) -> int:
    """'C' → 60, 'A' → 69, 'Bb' → 70 (en la octava 4)."""
    n = ALIAS.get(nombre, nombre)
    n = n[0].upper() + n[1:]
    if n not in NOMBRES:
        raise ValueError(f"tónica desconocida: {nombre}")
    return 12 * (octava + 1) + NOMBRES.index(n)


def frecuencia(nota: int) -> float:
    """Afinación temperada: A4 (MIDI 69) = 440 Hz y cada semitono multiplica por 2^(1/12). C4
    (60) ≈ 261.63 Hz.
    """
    return 440.0 * 2 ** ((nota - 69) / 12)


def nombre_nota(nota: int) -> str:
    """61 → 'C#4': la clase de altura sale del resto por 12 y la octava MIDI empieza en -1 (por
    eso 60 es C4).
    """
    return f"{NOMBRES[nota % 12]}{nota // 12 - 1}"


class Escala:
    """Escala a partir de una tónica MIDI y un modo (intervalos en semitonos desde la tónica).
    Calcula grados, acordes por terceras y pertenencia.
    """
    def __init__(self, tonica: int, modo: str = "mayor") -> None:
        """Valida el modo contra los conocidos."""
        if modo not in ESCALAS:
            raise ValueError(f"modo desconocido: {modo} (opciones: {', '.join(ESCALAS)})")
        self.tonica, self.modo, self.intervalos = tonica, modo, ESCALAS[modo]

    def grado(self, g: int) -> int:
        """Nota MIDI del grado ``g`` (0 = tónica). Admite grados negativos o mayores que la escala."""
        n = len(self.intervalos)
        octava, idx = divmod(g, n)
        return self.tonica + 12 * octava + self.intervalos[idx]

    def contiene(self, nota: int) -> bool:
        """True si la nota pertenece a la escala en cualquier octava."""
        return (nota - self.tonica) % 12 in self.intervalos

    def notas_en_rango(self, bajo: int, alto: int) -> list[int]:
        """Notas de la escala entre ``bajo`` y ``alto`` inclusive."""
        return [x for x in range(bajo, alto + 1) if self.contiene(x)]

    def acorde(self, grado: int) -> tuple[int, int, int]:
        """Tríada diatónica sobre el grado (0-based): grados g, g+2, g+4."""
        return (self.grado(grado), self.grado(grado + 2), self.grado(grado + 4))

    def clases_acorde(self, grado: int) -> set[int]:
        """Clases de altura (0-11) del acorde, para comprobar notas en cualquier octava."""
        return {n % 12 for n in self.acorde(grado)}
