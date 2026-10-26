"""Simulación del procesador de tarjetas.

No se contacta a ningún banco. Las tarjetas "de prueba" definen el resultado,
como en los entornos *sandbox* de las pasarelas reales.
"""
from __future__ import annotations

from dataclasses import dataclass

#: Tarjetas de prueba → motivo de rechazo (``None`` = aprobada).
TARJETAS_PRUEBA: dict[str, str | None] = {
    "4242424242424242": None,
    "5555555555554444": None,
    "4000000000000002": "tarjeta_rechazada",
    "4000000000009995": "fondos_insuficientes",
}


def luhn_valido(numero: str) -> bool:
    """Algoritmo de Luhn: detecta errores de tipeo en números de tarjeta."""
    if not numero.isdigit() or not 12 <= len(numero) <= 19:
        return False
    total = 0
    for i, d in enumerate(reversed(numero)):
        n = int(d)
        if i % 2 == 1:  # se duplica cada segundo dígito desde la derecha
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
    return total % 10 == 0


def marca(numero: str) -> str:
    """Marca aproximada según el prefijo (BIN)."""
    if numero.startswith("4"):
        return "visa"
    if numero[:2] in {"51", "52", "53", "54", "55"}:
        return "mastercard"
    if numero[:2] in {"34", "37"}:
        return "amex"
    return "desconocida"


@dataclass(frozen=True)
class Resultado:
    aprobado: bool
    motivo: str | None
    ultimos4: str
    marca: str


def procesar(numero: str, mes: int, anio: int, hoy_anio_mes: tuple[int, int]) -> Resultado:
    """Simula la autorización. Nunca se guarda el número completo: solo los 4 últimos."""
    numero = numero.replace(" ", "")
    if not luhn_valido(numero):
        return Resultado(False, "numero_invalido", numero[-4:], "desconocida")
    if (anio, mes) < hoy_anio_mes:
        return Resultado(False, "tarjeta_vencida", numero[-4:], marca(numero))
    # Tarjetas válidas fuera de la lista de prueba: se aprueban.
    motivo = TARJETAS_PRUEBA.get(numero)
    return Resultado(motivo is None, motivo, numero[-4:], marca(numero))
