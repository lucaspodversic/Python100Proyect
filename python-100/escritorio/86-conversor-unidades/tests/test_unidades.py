"""Tests del cálculo de conversiones (sin GUI)."""
from fractions import Fraction as F

import pytest

from conversor.unidades import MAGNITUDES, ErrorConversion, convertir, formatear, parsear, tabla_conversiones


@pytest.mark.parametrize("valor, mag, de, a, esperado", [
    # Definiciones legales exactas: 1 in = 2.54 cm, 1 mi = 1.609344 km, 1 lb = 453.59237 g.
    (1, "longitud", "in", "cm", F("2.54")), (1, "longitud", "mi", "km", F("1.609344")),
    (1, "masa", "lb", "g", F("453.59237")),
    # 16 oz = 1 lb (avoirdupois).
    (16, "masa", "oz", "lb", 1),
    # Puntos fijos de temperatura: ebullición (100 °C = 212 °F) y el cruce -40 °F = -40 °C.
    (100, "temperatura", "°C", "°F", 212), (-40, "temperatura", "°F", "°C", -40),
    # Cero absoluto y fusión del hielo (32 °F = 273.15 K); °R = °F + 459.67 → 491.67 °R = 32 °F.
    (0, "temperatura", "K", "°C", F("-273.15")), (32, "temperatura", "°F", "K", F("273.15")),
    (491.67, "temperatura", "°R", "°F", 32),
    # Galón estadounidense = 231 in³ = 3.785411784 l; 16 tazas = 1 galón.
    (1, "volumen", "gal", "l", F("3.785411784")), (16, "volumen", "cup", "gal", 1),
    # 1 semana = 7 × 24 = 168 h.
    (1, "tiempo", "sem", "h", 168),
])
def test_conversiones_exactas(valor, mag, de, a, esperado):
    """Cada conversión de la tabla es EXACTA (igualdad de Fraction, sin tolerancia)."""
    assert convertir(F(str(valor)), mag, de, a) == esperado


@pytest.mark.parametrize("mag", list(MAGNITUDES))
def test_ida_y_vuelta_exacta(mag):
    """Para todas las combinaciones de unidades de cada magnitud, ida y vuelta devuelve el
    valor original exacto.
    """
    # Para cualquier par de unidades, convertir y volver da exactamente el original.
    unidades = list(MAGNITUDES[mag])
    for de in unidades:
        for a in unidades:
            assert convertir(convertir(F("123.456"), mag, de, a), mag, a, de) == F("123.456")


# "1,5" con coma decimal = 3/2; espacios como separador de miles; notación científica.
@pytest.mark.parametrize("texto, esperado", [("1,5", F(3, 2)), (" 1 000.25 ", F("1000.25")), ("-2e3", -2000)])
def test_parsear(texto, esperado):
    """Acepta coma decimal, espacios como separador de miles y notación científica."""
    assert parsear(texto) == esperado


# "1.234,5" es ambiguo (¿miles europeos?): se rechaza en vez de adivinar.
@pytest.mark.parametrize("texto", ["abc", "", "1.234,5", "inf", "nan"])
def test_parsear_invalido(texto):
    """Texto, vacío, formatos ambiguos (punto de miles + coma decimal) e infinitos/NaN se
    rechazan.
    """
    with pytest.raises(ErrorConversion):
        parsear(texto)


def test_errores_fisicos_y_unidades():
    """-300 °C está por debajo del cero absoluto (-273.15); una masa negativa no existe; un
    tiempo negativo sí (es una duración relativa). Unidad de otra magnitud o magnitud
    inexistente → error claro.
    """
    with pytest.raises(ErrorConversion, match="cero absoluto"):
        convertir(-300, "temperatura", "°C", "K")
    with pytest.raises(ErrorConversion, match="negativa"):
        convertir(-1, "masa", "kg", "g")
    assert convertir(-5, "tiempo", "min", "s") == -300   # tiempo relativo sí puede ser negativo
    with pytest.raises(ErrorConversion, match="unidad"):
        convertir(1, "masa", "kg", "m")
    with pytest.raises(ErrorConversion, match="magnitud"):
        convertir(1, "energía", "J", "cal")


def test_formatear_y_tabla():
    """1/3 se muestra con 10 decimales; 10^20 en notación científica compacta; sin ceros
    sobrantes ('2.50' → '2.5'). 1 m = 1000 mm y 1/0.3048 = 3.280839895 ft (redondeado a
    10 decimales).
    """
    assert formatear(F(1, 3)) == "0.3333333333"
    assert formatear(F(10) ** 20) == "1e20" and formatear(F(0)) == "0"
    assert formatear(F("2.50")) == "2.5"
    filas = dict(tabla_conversiones(F(1), "longitud", "m"))
    assert filas["milímetro (mm)"] == "1000" and filas["pie (ft)"] == "3.280839895"
