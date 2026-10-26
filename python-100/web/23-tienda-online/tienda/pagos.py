"""Pasarela de pago SIMULADA.

Define una interfaz (`PasarelaPago`) para que en producción se pueda enchufar
un proveedor real (Stripe, Mercado Pago...) sin tocar la lógica de la tienda.
La implementación incluida NO cobra nada: imita el comportamiento de las
tarjetas de prueba típicas de las pasarelas.

Regla de oro: el número completo de tarjeta nunca se guarda ni se loguea; solo
se conservan los últimos 4 dígitos.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Protocol


# frozen: el resultado es inmutable (nadie puede "aprobar" un pago después).
@dataclass(frozen=True)
class ResultadoPago:
    """Respuesta normalizada de la pasarela."""
    aprobado: bool
    id_transaccion: str | None
    motivo: str
    ultimos4: str


# Protocol = tipado estructural: cualquier clase con un método `cobrar`
# compatible sirve, sin necesidad de heredar.
class PasarelaPago(Protocol):
    """Contrato mínimo que debe cumplir cualquier pasarela."""

    def cobrar(self, importe_centavos: int, numero_tarjeta: str, cvv: str, vencimiento: str) -> ResultadoPago: ...


def luhn_valido(numero: str) -> bool:
    """Valida el dígito verificador de una tarjeta con el algoritmo de Luhn."""
    # Las tarjetas reales tienen entre 12 y 19 dígitos (norma ISO/IEC 7812).
    if not numero.isdigit() or not 12 <= len(numero) <= 19:
        return False
    total = 0
    # Se recorre de derecha a izquierda duplicando uno de cada dos dígitos
    for i, c in enumerate(reversed(numero)):
        d = int(c)
        if i % 2 == 1:
            d *= 2
            # Restar 9 equivale a sumar los dígitos del doble (ej.: 8*2=16 -> 1+6=7 = 16-9).
            if d > 9:
                d -= 9
        total += d
    # El número es válido si la suma total es múltiplo de 10.
    return total % 10 == 0


# Tarjetas de prueba que se rechazan con un motivo concreto
# Mismos números que usa Stripe en su modo de prueba (pasan Luhn pero se
# rechazan), así el comportamiento resulta familiar.
TARJETAS_RECHAZADAS = {
    "4000000000000002": "Tarjeta rechazada",
    "4000000000009995": "Fondos insuficientes",
}


class PasarelaSimulada:
    """Pasarela de pruebas: aprueba cualquier tarjeta válida salvo las de la lista negra."""

    def __init__(self) -> None:
        # Registro de cobros aprobados (id -> importe), útil para tests y reembolsos
        self.cobros: dict[str, int] = {}

    def cobrar(self, importe_centavos: int, numero_tarjeta: str, cvv: str, vencimiento: str) -> ResultadoPago:
        # Se aceptan formatos con espacios o guiones ("4242 4242 ...").
        numero = numero_tarjeta.replace(" ", "").replace("-", "")
        # Lo único que se conserva de la tarjeta.
        ult4 = numero[-4:]
        # Validaciones en orden: importe, número, CVV, vencimiento y lista negra.
        if importe_centavos <= 0:
            return ResultadoPago(False, None, "Importe inválido", ult4)
        if not luhn_valido(numero):
            return ResultadoPago(False, None, "Número de tarjeta inválido", ult4)
        if not (cvv.isdigit() and len(cvv) in (3, 4)):
            return ResultadoPago(False, None, "CVV inválido", ult4)
        if not _vencimiento_valido(vencimiento):
            return ResultadoPago(False, None, "Tarjeta vencida o fecha inválida", ult4)
        if numero in TARJETAS_RECHAZADAS:
            return ResultadoPago(False, None, TARJETAS_RECHAZADAS[numero], ult4)
        # Id de transacción aleatorio, al estilo de las pasarelas reales.
        tx = "tx_" + secrets.token_hex(8)
        self.cobros[tx] = importe_centavos
        return ResultadoPago(True, tx, "Aprobado", ult4)


def _vencimiento_valido(mm_aa: str, hoy: tuple[int, int] | None = None) -> bool:
    """Valida un vencimiento 'MM/AA' que no esté en el pasado."""
    # Import local: solo se necesita acá.
    from datetime import date
    try:
        mm, aa = mm_aa.split("/")
        mes, anio = int(mm), 2000 + int(aa)
    # Cubre "1230" (sin "/", falla el unpack) y "ab/cd" (falla int()).
    except ValueError:
        return False
    if not 1 <= mes <= 12:
        return False
    # `hoy` es inyectable para que los tests no dependan de la fecha real.
    a, m = hoy or (date.today().year, date.today().month)
    # Comparación de tuplas (año, mes): una tarjeta vence al terminar su mes,
    # por eso el mes actual todavía es válido (>=).
    return (anio, mes) >= (a, m)
