"""Cálculos monetarios con `Decimal`.

Por qué Decimal: con float, 0.1 + 0.2 != 0.3 y al dividir una cuenta
los centavos "se pierden". Aquí todo se cuantiza a centavos con
ROUND_HALF_UP (redondeo comercial) y el reparto entre personas
distribuye el resto centavo a centavo para que la suma sea EXACTA.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, InvalidOperation

# Unidad mínima: todo se redondea a 2 decimales.
CENTAVO = Decimal("0.01")


def a_decimal(valor: str | int | Decimal, nombre: str = "valor") -> Decimal:
    """Convierte aceptando coma decimal ('12,50') y valida que no sea negativo."""
    try:
        # str() primero: así un int o un Decimal pasan por el mismo camino que el texto.
        d = Decimal(str(valor).strip().replace(",", "."))
    except InvalidOperation:
        raise ValueError(f"{nombre} no es un número: {valor!r}") from None
    # Decimal acepta "inf" y "NaN": se rechazan antes de comparar (comparar NaN con < daría error).
    if not d.is_finite() or d < 0:
        raise ValueError(f"{nombre} debe ser un número no negativo")
    return d


def centavos(d: Decimal) -> Decimal:
    """Redondea a centavos con redondeo comercial (0,005 → 0,01)."""
    return d.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def repartir(total: Decimal, personas: int) -> list[Decimal]:
    """Divide `total` en `personas` partes que suman exactamente `total`.

    Ej.: 100 / 3 → [33.34, 33.33, 33.33].
    """
    # Caso borde: evita dividir por cero o por un número negativo.
    if personas < 1:
        raise ValueError("Debe haber al menos una persona")
    total_c = int(centavos(total) / CENTAVO)  # en centavos enteros
    # Todos reciben `base` centavos y los primeros `resto` reciben uno más: la suma da exacta.
    base, resto = divmod(total_c, personas)
    return [Decimal(base + (1 if i < resto else 0)) * CENTAVO for i in range(personas)]


@dataclass(frozen=True)
class Cuenta:
    """Datos de entrada: subtotal, % de propina, personas, impuesto y redondeo."""
    subtotal: Decimal
    porcentaje: Decimal = Decimal("10")
    personas: int = 1
    impuesto: Decimal = Decimal("0")   # % de impuesto a sumar (0 si ya está incluido)
    propina_sobre_impuesto: bool = False
    redondear_a: Decimal | None = None  # p. ej. 1 → total redondeado hacia arriba al entero


@dataclass(frozen=True)
class Resultado:
    """Montos calculados, ya redondeados a centavos."""
    impuesto: Decimal
    propina: Decimal
    total: Decimal
    por_persona: list[Decimal]
    porcentaje_efectivo: Decimal  # cambia si se redondeó el total


def calcular(c: Cuenta) -> Resultado:
    """Calcula impuesto, propina, total y reparto entre personas."""
    if c.porcentaje < 0 or c.porcentaje > 100:
        raise ValueError("El porcentaje de propina debe estar entre 0 y 100")
    # El impuesto (p. ej. IVA 21 %) se suma sólo si no estaba incluido en el subtotal.
    imp = centavos(c.subtotal * c.impuesto / 100)
    # Por defecto la propina se calcula sobre el subtotal sin impuesto.
    base = c.subtotal + imp if c.propina_sobre_impuesto else c.subtotal
    propina = centavos(base * c.porcentaje / 100)
    total = c.subtotal + imp + propina
    if c.redondear_a:
        # Redondeo hacia arriba al múltiplo pedido; la diferencia va a la propina
        total = (total / c.redondear_a).to_integral_value(rounding=ROUND_CEILING) * c.redondear_a
        propina = total - c.subtotal - imp
    # Se normaliza a 2 decimales (redondear a un múltiplo entero puede dejar otro exponente).
    total = centavos(total)
    # Porcentaje real de propina tras el redondeo; con base 0 se evita dividir por cero.
    efectivo = centavos(propina * 100 / base) if base else Decimal("0.00")
    return Resultado(imp, centavos(propina), total, repartir(total, c.personas), efectivo)
