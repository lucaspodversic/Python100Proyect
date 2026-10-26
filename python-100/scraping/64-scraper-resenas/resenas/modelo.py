"""Modelo de una reseña y normalización de calificaciones."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Resena:
    """Una reseña normalizada, venga del parser CSS o de JSON-LD."""
    autor: str
    texto: str
    estrellas: float | None = None   # normalizado a escala 1-5
    # Campos opcionales: no todos los sitios los publican.
    titulo: str = ""
    fecha: str = ""
    verificada: bool = False


def parsear_estrellas(texto: str, maximo: float = 5.0) -> float | None:
    """'4,0 de 5 estrellas' → 4.0 ; '8/10' → 4.0 ; '★★★☆☆' → 3.0."""
    if not texto:
        return None
    # Estrellas dibujadas: llenas / total, llevado a escala 5.
    if "★" in texto:
        return float(texto.count("★")) * 5 / max(1, texto.count("★") + texto.count("☆"))
    # Formato "valor de/sobre/out of/ tope" (acepta coma decimal).
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:/|de|out of|sobre)\s*(\d+)", texto)
    if m:
        valor, tope = float(m.group(1).replace(",", ".")), float(m.group(2))
    else:
        # Un número suelto se interpreta en la escala `maximo`.
        m = re.search(r"\d+(?:[.,]\d+)?", texto)
        if not m:
            return None
        valor, tope = float(m.group(0).replace(",", ".")), maximo
    # Valores imposibles (p. ej. "7 de 5") se descartan en vez de inventar un dato.
    if tope <= 0 or not 0 <= valor <= tope:
        return None
    # Regla de tres a escala 1-5.
    return round(valor * 5 / tope, 2)
