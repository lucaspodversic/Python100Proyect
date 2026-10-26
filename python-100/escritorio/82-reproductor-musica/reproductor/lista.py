"""Lista de reproducción pura: orden, aleatorio reproducible y modos de repetición."""
from __future__ import annotations

import random
from enum import Enum
from pathlib import Path

#: Formatos que pygame.mixer.music suele soportar.
EXTENSIONES = {".mp3", ".ogg", ".wav", ".flac"}


class Repetir(str, Enum):
    """Modos de repetición. Solo afectan al avance automático (fin de pista); los botones
    manuales siempre se mueven.
    """
    NO = "no"          # al terminar la última, se detiene
    TODAS = "todas"    # vuelve a la primera
    UNA = "una"        # repite la pista actual


def escanear(carpeta: Path) -> list[Path]:
    """Devuelve los archivos de audio de ``carpeta`` (recursivo), ordenados por nombre."""
    return sorted((p for p in carpeta.rglob("*") if p.is_file() and p.suffix.lower() in EXTENSIONES),
                  key=lambda p: str(p).lower())


class ListaReproduccion:
    """Mantiene las pistas y el índice actual.

    ``orden`` es una permutación de índices: en modo normal es 0..n-1 y en
    aleatorio se baraja con un ``random.Random`` propio (sembrable en tests).
    """

    def __init__(self, pistas: list[Path] | None = None, semilla: int | None = None) -> None:
        """``orden`` es una permutación de índices de ``pistas``: en modo normal es 0..n-1 y en
        aleatorio se baraja, así las pistas nunca se copian ni se reordenan.
        ``semilla`` hace el barajado reproducible en tests.
        """
        self.pistas: list[Path] = list(pistas or [])
        self.orden: list[int] = list(range(len(self.pistas)))
        self.pos: int = 0                    # posición dentro de ``orden``
        self.aleatorio = False
        self.repetir = Repetir.NO
        self._rng = random.Random(semilla)

    # ------------------------------------------------------------ consulta
    @property
    def actual(self) -> Path | None:
        """Pista actual o None si la lista está vacía."""
        return self.pistas[self.orden[self.pos]] if self.pistas else None

    def __len__(self) -> int:
        """Cantidad de pistas."""
        return len(self.pistas)

    # ------------------------------------------------------------ edición
    def agregar(self, *rutas: Path) -> None:
        """Agrega al final; el índice nuevo también se agrega al final del orden (aunque esté
        en aleatorio).
        """
        for ruta in rutas:
            self.pistas.append(ruta)
            self.orden.append(len(self.pistas) - 1)

    def quitar(self, indice: int) -> None:
        """Quita la pista ``indice`` (en el orden original) ajustando la posición actual."""
        if not 0 <= indice < len(self.pistas):
            raise IndexError("índice fuera de rango")
        actual = self.orden[self.pos] if self.pistas else None
        del self.pistas[indice]
        # Reindexar la permutación: se quita ``indice`` y se corren los mayores.
        self.orden = [i - (i > indice) for i in self.orden if i != indice]
        if not self.pistas:
            self.pos = 0
        elif actual is not None and actual != indice:
            self.pos = self.orden.index(actual - (actual > indice))
        else:
            self.pos = min(self.pos, len(self.orden) - 1)

    def ir_a(self, indice: int) -> Path:
        """Salta a la pista ``indice`` del orden original."""
        self.pos = self.orden.index(indice)
        return self.pistas[indice]

    def alternar_aleatorio(self) -> None:
        """Activa/desactiva aleatorio conservando la pista actual como primera."""
        if not self.pistas:
            self.aleatorio = not self.aleatorio
            return
        actual = self.orden[self.pos]
        self.aleatorio = not self.aleatorio
        if self.aleatorio:
            resto = [i for i in range(len(self.pistas)) if i != actual]
            self._rng.shuffle(resto)
            self.orden = [actual, *resto]
            self.pos = 0
        else:
            self.orden = list(range(len(self.pistas)))
            self.pos = actual

    # ------------------------------------------------------------ navegación
    def siguiente(self, automatico: bool = False) -> Path | None:
        """Avanza. ``automatico`` indica fin natural de pista (respeta Repetir.UNA).

        Devuelve ``None`` si se llegó al final sin repetición.
        """
        if not self.pistas:
            return None
        if automatico and self.repetir is Repetir.UNA:
            return self.actual
        if self.pos + 1 < len(self.orden):
            self.pos += 1
        elif self.repetir is Repetir.TODAS or not automatico:
            # Botón "siguiente" manual en la última pista: vuelve al principio.
            self.pos = 0
        else:
            return None
        return self.actual

    def anterior(self) -> Path | None:
        """Retrocede una posición con vuelta (desde la primera va a la última)."""
        if not self.pistas:
            return None
        self.pos = (self.pos - 1) % len(self.orden)
        return self.actual
