"""Reglas de longitud de publicaciones y partición en hilos.

X cuenta "caracteres ponderados" (biblioteca twitter-text):

* cada URL cuenta **23**, sea cual sea su largo (se acorta con t.co);
* caracteres latinos y de puntuación comunes pesan 1;
* el resto (CJK, emojis…) pesan 2;
* el límite para cuentas estándar es 280.

Esta es una aproximación fiel para la mayoría de los textos.
"""
from __future__ import annotations

import re
import unicodedata

LIMITE = 280
PESO_URL = 23
_URL = re.compile(r"https?://\S+", re.IGNORECASE)
# Rangos de peso 1 según la configuración v3 de twitter-text.
_RANGOS_PESO_1 = ((0x0000, 0x10FF), (0x2000, 0x200D), (0x2010, 0x201F), (0x2032, 0x2037))


def _peso(c: str) -> int:
    """Peso de un carácter según X: 1 para latinos y comunes, 2 para el resto (CJK, emoji,
    etc.).
    """
    cp = ord(c)
    return 1 if any(a <= cp <= b for a, b in _RANGOS_PESO_1) else 2


def longitud(texto: str) -> int:
    """Longitud ponderada (normalizando a NFC como hace X)."""
    texto = unicodedata.normalize("NFC", texto)
    total, pos = 0, 0
    for m in _URL.finditer(texto):
        total += sum(_peso(c) for c in texto[pos:m.start()]) + PESO_URL
        pos = m.end()
    return total + sum(_peso(c) for c in texto[pos:])


def restantes(texto: str) -> int:
    """Caracteres disponibles (negativo si se pasó)."""
    return LIMITE - longitud(texto)


def validar(texto: str) -> None:
    """Rechaza posts vacíos o que excedan el límite ponderado."""
    if not texto.strip():
        raise ValueError("la publicación está vacía")
    if longitud(texto) > LIMITE:
        raise ValueError(f"la publicación excede {LIMITE} caracteres ({longitud(texto)})")


def dividir_en_hilo(texto: str, limite: int = LIMITE) -> list[str]:
    """Parte un texto largo en publicaciones numeradas ``(i/n)`` sin cortar palabras.

    Se reserva espacio para el sufijo. Una "palabra" más larga que el límite
    (raro) se corta a la fuerza.
    """
    texto = " ".join(texto.split())
    if longitud(texto) <= limite:
        return [texto] if texto else []
    reserva = len(" (99/99)")
    partes: list[str] = []
    actual = ""
    for palabra in texto.split(" "):
        while longitud(palabra) > limite - reserva:  # palabra gigante
            corte = limite - reserva
            if actual:
                partes.append(actual); actual = ""
            partes.append(palabra[:corte]); palabra = palabra[corte:]
        candidato = f"{actual} {palabra}".strip()
        if longitud(candidato) <= limite - reserva:
            actual = candidato
        else:
            partes.append(actual)
            actual = palabra
    if actual:
        partes.append(actual)
    n = len(partes)
    return [f"{p} ({i}/{n})" for i, p in enumerate(partes, start=1)]
