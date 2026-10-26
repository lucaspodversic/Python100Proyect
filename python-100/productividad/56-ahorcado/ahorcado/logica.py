"""Lógica pura de una partida.

Las tildes y la diéresis se ignoran al comparar (adivinar "u" revela "ü"),
pero la "ñ" se considera una letra distinta, como en el alfabeto español.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from enum import Enum

from .palabras import ETAPAS


def normalizar(letra: str) -> str:
    """Quita tildes/diéresis conservando la ñ. 'Á' → 'a', 'ñ' → 'ñ'."""
    letra = letra.lower()
    # Caso especial: NFD separaría la ñ en "n" + tilde, y en español es una letra propia.
    if letra == "ñ":
        return letra
    # NFD separa la letra base de sus marcas (á → a + ´); las marcas (categoría "Mn") se descartan.
    base = unicodedata.normalize("NFD", letra)
    return "".join(c for c in base if unicodedata.category(c) != "Mn")


# Resultado de un intento, para que la interfaz decida qué mensaje mostrar.
class Resultado(Enum):
    ACIERTO = "acierto"
    FALLO = "fallo"
    REPETIDA = "repetida"
    INVALIDA = "inválida"


@dataclass
class Partida:
    """Estado de una partida: letras intentadas, fallos y palabra secreta."""
    palabra: str
    # 7 dibujos → 6 fallos permitidos (el primer dibujo es la horca vacía).
    max_fallos: int = len(ETAPAS) - 1
    intentadas: set[str] = field(default_factory=set)
    fallos: int = 0

    def __post_init__(self) -> None:
        # Se compara siempre en minúsculas.
        self.palabra = self.palabra.lower()
        # letras normalizadas que hay que descubrir (ignora espacios/guiones)
        self._objetivo = {normalizar(c) for c in self.palabra if c.isalpha()}

    def intentar(self, entrada: str) -> Resultado:
        """Procesa una letra o una palabra completa y devuelve el resultado."""
        entrada = entrada.strip().lower()
        # Caso borde: no se aceptan intentos después del final.
        if self.terminada():
            raise RuntimeError("La partida ya terminó")
        if len(entrada) > 1:  # intento de palabra completa
            # Arriesgar la palabra también ignora tildes ("funcion" acierta "función"); si acierta se descubren todas las letras.
            if "".join(map(normalizar, entrada)) == "".join(map(normalizar, self.palabra)):
                self.intentadas |= self._objetivo
                return Resultado.ACIERTO
            # Una palabra errada cuesta un fallo (pero no se registra como letra intentada).
            self.fallos += 1
            return Resultado.FALLO
        # Aquí sólo queda el caso vacío o un carácter que no es letra (números, signos).
        if len(entrada) != 1 or not entrada.isalpha():
            return Resultado.INVALIDA
        letra = normalizar(entrada)
        # Repetir una letra no penaliza.
        if letra in self.intentadas:
            return Resultado.REPETIDA
        self.intentadas.add(letra)
        if letra in self._objetivo:
            return Resultado.ACIERTO
        self.fallos += 1
        return Resultado.FALLO

    def mascara(self) -> str:
        """Palabra con '_' en las letras no descubiertas (conserva tildes)."""
        # Espacios y guiones se muestran siempre; las letras descubiertas, con su tilde original.
        return " ".join(c if not c.isalpha() or normalizar(c) in self.intentadas else "_" for c in self.palabra)

    def gano(self) -> bool:
        """Ganó si todas las letras objetivo están entre las intentadas."""
        return self._objetivo <= self.intentadas

    def perdio(self) -> bool:
        """Perdió al llegar al máximo de fallos."""
        return self.fallos >= self.max_fallos

    def terminada(self) -> bool:
        """La partida termina al ganar o perder."""
        return self.gano() or self.perdio()

    def dibujo(self) -> str:
        # Escala los fallos a las etapas disponibles si max_fallos es distinto
        # Con max_fallos = 6 coincide 1 a 1; max(1, ...) evita dividir por cero.
        idx = min(len(ETAPAS) - 1, self.fallos * (len(ETAPAS) - 1) // max(1, self.max_fallos))
        return ETAPAS[idx]

    def fallidas(self) -> list[str]:
        """Letras intentadas que no están en la palabra, ordenadas."""
        return sorted(self.intentadas - self._objetivo)
