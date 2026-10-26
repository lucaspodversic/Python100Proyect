"""Tests unitarios del cálculo de nómina (funciones puras)."""
from datetime import date
from decimal import Decimal

import pytest

from app import nomina


def test_liquidacion_sin_ausencias():
    liq = nomina.liquidar(100_000_00, 0)
    assert liq.aportes == 17_000_00          # 17 % de 100.000
    assert liq.neto == 83_000_00
    assert liq.descuento_ausencias == 0


def test_descuento_por_dias_sin_goce():
    liq = nomina.liquidar(90_000_00, 3)      # 90.000 / 30 × 3 = 9.000
    assert liq.descuento_ausencias == 9_000_00
    assert liq.neto == 81_000_00 - round(81_000_00 * 0.17)


def test_redondeo_half_up_y_aportes_personalizados():
    assert nomina.redondear(Decimal("10.5")) == 11
    liq = nomina.liquidar(1001, 0, {"x": Decimal("0.5")})
    assert liq.aportes == 501 and liq.neto == 500


def test_dias_en_periodo_e_intersecciones():
    assert nomina.dias_en_periodo(date(2026, 1, 28), date(2026, 2, 3), "2026-02") == 3
    assert nomina.dias_en_periodo(date(2026, 1, 1), date(2026, 1, 5), "2026-02") == 0
    assert nomina.rango_periodo("2024-02")[1] == date(2024, 2, 29)  # año bisiesto
    with pytest.raises(ValueError):
        nomina.rango_periodo("2026-13")
    with pytest.raises(ValueError):
        nomina.liquidar(-1, 0)
