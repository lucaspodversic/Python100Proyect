"""Cálculo de nómina como funciones puras (fáciles de testear).

Se usa ``Decimal`` con redondeo *half-up* a centavos, como en contabilidad.
Los porcentajes de aportes son configurables; por defecto se usan los aportes
del empleado en Argentina (jubilación 11 %, obra social 3 %, PAMI 3 %), solo
como ejemplo didáctico.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

# Porcentajes de aportes del empleado (ejemplo; ajustar a la legislación vigente).
APORTES_POR_DEFECTO: dict[str, Decimal] = {
    "jubilacion": Decimal("0.11"),
    "obra_social": Decimal("0.03"),
    "pami": Decimal("0.03"),
}


def redondear(valor: Decimal) -> int:
    """Redondea a centavo entero con *half-up* (0,5 sube)."""
    return int(valor.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def rango_periodo(periodo: str) -> tuple[date, date]:
    """Devuelve el primer y el último día de un período ``AAAA-MM``."""
    anio, mes = (int(x) for x in periodo.split("-"))
    if not 1 <= mes <= 12:
        raise ValueError("mes inválido")
    return date(anio, mes, 1), date(anio, mes, calendar.monthrange(anio, mes)[1])


def dias_en_periodo(desde: date, hasta: date, periodo: str) -> int:
    """Días de ``[desde, hasta]`` que caen dentro del período (intersección)."""
    inicio, fin = rango_periodo(periodo)
    a, b = max(desde, inicio), min(hasta, fin)
    return max(0, (b - a).days + 1)


@dataclass(frozen=True)
class Liquidacion:
    """Resultado del cálculo de una nómina (todo en centavos)."""

    bruto: int
    descuento_ausencias: int
    aportes: int
    neto: int


def liquidar(bruto_centavos: int, dias_sin_goce: int,
             aportes: dict[str, Decimal] | None = None) -> Liquidacion:
    """Calcula la nómina mensual.

    El descuento por ausencia sin goce es ``bruto / 30 × días`` (mes comercial
    de 30 días). Los aportes se aplican sobre el bruto ya descontado.
    """
    if bruto_centavos < 0 or dias_sin_goce < 0:
        raise ValueError("valores negativos no permitidos")
    aportes = APORTES_POR_DEFECTO if aportes is None else aportes
    bruto = Decimal(bruto_centavos)
    descuento = redondear(bruto / 30 * min(dias_sin_goce, 30))
    base = bruto - descuento
    total_aportes = redondear(base * sum(aportes.values(), Decimal(0)))
    return Liquidacion(bruto_centavos, descuento, total_aportes, int(base) - total_aportes)
