"""Tests exactos con Decimal."""
from decimal import Decimal as D

import pytest

from propinas import Cuenta, calcular, repartir
from propinas.calculo import a_decimal
from propinas.cli import ejecutar, formato


# 100 / 3 y 5 centavos entre 7: la suma siempre es exacta; 0 personas es error.
def test_repartir_suma_exacta():
    partes = repartir(D("100"), 3)
    assert partes == [D("33.34"), D("33.33"), D("33.33")] and sum(partes) == D("100.00")
    assert sum(repartir(D("0.05"), 7)) == D("0.05")
    with pytest.raises(ValueError):
        repartir(D("1"), 0)


# 15 % de 85,40 = 12,81 → total 98,21 → 49,11 + 49,10.
def test_calculo_basico():
    r = calcular(Cuenta(D("85.40"), D("15"), 2))
    assert (r.propina, r.total) == (D("12.81"), D("98.21"))
    assert r.por_persona == [D("49.11"), D("49.10")]


# Propina sobre el subtotal (10,00) o incluyendo el impuesto (10 % de 121 = 12,10).
def test_impuesto():
    r = calcular(Cuenta(D("100"), D("10"), impuesto=D("21")))
    assert (r.impuesto, r.propina, r.total) == (D("21.00"), D("10.00"), D("131.00"))
    r2 = calcular(Cuenta(D("100"), D("10"), impuesto=D("21"), propina_sobre_impuesto=True))
    assert r2.propina == D("12.10")


# 1234 + 123,40 = 1357,40 → redondeado a 1400; la propina absorbe la diferencia (13,45 % efectivo).
def test_redondeo_hacia_arriba():
    r = calcular(Cuenta(D("1234"), D("10"), 4, redondear_a=D("100")))
    assert r.total == D("1400.00") and r.propina == D("166.00")
    assert r.porcentaje_efectivo == D("13.45") and sum(r.por_persona) == r.total


# Coma decimal aceptada; texto, negativo, infinito y NaN rechazados; propina mayor a 100 % rechazada.
def test_validaciones():
    assert a_decimal("12,5") == D("12.5")
    for malo in ("abc", "-3", "inf", "NaN"):
        with pytest.raises(ValueError):
            a_decimal(malo)
    with pytest.raises(ValueError):
        calcular(Cuenta(D("10"), D("150")))


# Formato rioplatense y reparto de 110 entre 3 en la salida.
def test_cli(capsys):
    assert formato(D("1234567.5")) == "$1.234.567,50"
    assert ejecutar(["100", "-n", "3"]) == 0
    out = capsys.readouterr().out
    assert "Total:      $110,00" in out and "2×$36,67 / 1×$36,66" in out
    assert ejecutar(["x"]) == 1
