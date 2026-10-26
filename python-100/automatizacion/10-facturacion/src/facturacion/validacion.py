"""Reglas de validación antes de contabilizar."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from .extractor import DatosFactura

# Subtotal e IVA no son obligatorios: hay facturas sin IVA discriminado (p. ej. monotributo).
OBLIGATORIOS = ("numero", "fecha", "proveedor", "total")


def validar(d: DatosFactura, hoy: dt.date | None = None, tolerancia: Decimal = Decimal("0.02")) -> list[str]:
    """Devuelve la lista de problemas (vacía = OK)."""
    hoy = hoy or dt.date.today()
    # Se acumulan TODOS los errores (no se corta en el primero) para que la revisión sea completa.
    errores = [f"falta {c}" for c in OBLIGATORIOS if getattr(d, c) in (None, "")]
    if d.total is not None and d.total <= 0:
        errores.append("total no positivo")
    if d.fecha and d.fecha > hoy:
        errores.append("fecha futura")
    # Consistencia aritmética sólo si están los tres importes; tolerancia de 2 centavos por redondeos.
    if None not in (d.subtotal, d.iva, d.total):
        assert d.subtotal is not None and d.iva is not None and d.total is not None
        if abs(d.subtotal + d.iva - d.total) > tolerancia:
            errores.append(f"subtotal+IVA ({d.subtotal + d.iva}) != total ({d.total})")
    return errores
