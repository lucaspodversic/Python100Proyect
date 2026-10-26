"""Conversión de unidades con aritmética **exacta** (``fractions.Fraction``).

Cada unidad se define como una transformación afín hacia la unidad base de
su magnitud: ``base = valor * factor + desplazamiento``. Para longitud o masa
el desplazamiento es 0; para temperatura no (°C → K suma 273,15).

Usar ``Fraction`` evita errores de coma flotante en cadenas de conversiones:
1 milla → m → milla devuelve exactamente 1.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction as F


class ErrorConversion(ValueError):
    """Entrada no numérica, unidad desconocida o valor físicamente imposible."""


@dataclass(frozen=True)
class Unidad:
    """Unidad lineal respecto de la unidad base de su magnitud: base = valor·factor +
    desplazamiento. El desplazamiento solo se usa en temperatura (°C → K suma 273.15).
    Todo en ``Fraction`` para que las conversiones sean exactas.
    """
    simbolo: str
    nombre: str
    factor: F
    desplazamiento: F = F(0)

    def a_base(self, valor: F) -> F:
        """Convierte de esta unidad a la unidad base de la magnitud."""
        return valor * self.factor + self.desplazamiento

    def desde_base(self, base: F) -> F:
        """Inversa exacta de ``a_base``."""
        return (base - self.desplazamiento) / self.factor


def _u(simbolo: str, nombre: str, factor: str | int, desplaz: str | int = 0) -> Unidad:
    """Atajo para declarar unidades en las tablas de MAGNITUDES."""
    # Los factores se escriben como texto ("0.0254") para que Fraction sea exacta.
    return Unidad(simbolo, nombre, F(factor), F(desplaz))


#: Magnitud → unidades. Base: metro, kilogramo, kelvin, litro, segundo.
MAGNITUDES: dict[str, dict[str, Unidad]] = {
    "longitud": {u.simbolo: u for u in (
        _u("mm", "milímetro", "0.001"), _u("cm", "centímetro", "0.01"), _u("m", "metro", 1),
        _u("km", "kilómetro", 1000), _u("in", "pulgada", "0.0254"), _u("ft", "pie", "0.3048"),
        _u("yd", "yarda", "0.9144"), _u("mi", "milla", "1609.344"), _u("nmi", "milla náutica", 1852),
    )},
    "masa": {u.simbolo: u for u in (
        _u("mg", "miligramo", "0.000001"), _u("g", "gramo", "0.001"), _u("kg", "kilogramo", 1),
        _u("t", "tonelada", 1000), _u("oz", "onza", "0.028349523125"), _u("lb", "libra", "0.45359237"),
        _u("st", "stone", "6.35029318"),
    )},
    "temperatura": {u.simbolo: u for u in (
        _u("K", "kelvin", 1), _u("°C", "grado Celsius", 1, "273.15"),
        # °F → K: (F − 32)·5/9 + 273.15 = F·5/9 + (273.15 − 160/9)
        Unidad("°F", "grado Fahrenheit", F(5, 9), F("273.15") - F(160, 9)),
        _u("°R", "grado Rankine", F(5, 9)),
    )},
    "volumen": {u.simbolo: u for u in (
        _u("ml", "mililitro", "0.001"), _u("l", "litro", 1), _u("m³", "metro cúbico", 1000),
        _u("tsp", "cucharadita (EE. UU.)", "0.00492892159375"), _u("cup", "taza (EE. UU.)", "0.2365882365"),
        _u("gal", "galón (EE. UU.)", "3.785411784"),
    )},
    "tiempo": {u.simbolo: u for u in (
        _u("ms", "milisegundo", "0.001"), _u("s", "segundo", 1), _u("min", "minuto", 60),
        _u("h", "hora", 3600), _u("d", "día", 86400), _u("sem", "semana", 604800),
    )},
}

#: Magnitudes donde el valor base no puede ser negativo (no hay -3 kg ni -5 K).
NO_NEGATIVAS = {"longitud", "masa", "temperatura", "volumen"}


def parsear(texto: str) -> F:
    """Convierte texto a Fraction. Acepta coma decimal y separadores de miles con espacio.

    ``"1.234,5"`` es ambiguo y se rechaza para no adivinar mal.
    """
    t = texto.strip().replace(" ", "").replace("\u00a0", "")
    if "," in t and "." in t:
        raise ErrorConversion("usá solo coma o solo punto como separador decimal")
    t = t.replace(",", ".")
    try:
        d = Decimal(t)
    except InvalidOperation as e:
        raise ErrorConversion(f"«{texto}» no es un número") from e
    if not d.is_finite():
        raise ErrorConversion("el número debe ser finito")
    return F(d)


def convertir(valor: F | int | str, magnitud: str, de: str, a: str) -> F:
    """Convierte ``valor`` de la unidad ``de`` a la unidad ``a`` dentro de ``magnitud``."""
    if magnitud not in MAGNITUDES:
        raise ErrorConversion(f"magnitud desconocida: {magnitud}")
    tabla = MAGNITUDES[magnitud]
    for s in (de, a):
        if s not in tabla:
            raise ErrorConversion(f"unidad desconocida para {magnitud}: {s}")
    v = parsear(valor) if isinstance(valor, str) else F(valor)
    base = tabla[de].a_base(v)
    if magnitud in NO_NEGATIVAS and base < 0:
        raise ErrorConversion("por debajo del cero absoluto" if magnitud == "temperatura"
                              else f"una {magnitud} no puede ser negativa")
    return tabla[a].desde_base(base)


def formatear(valor: F, cifras: int = 10) -> str:
    """Muestra con ``cifras`` significativas, sin ceros sobrantes y con notación científica si hace falta."""
    if valor == 0:
        return "0"
    texto = f"{float(valor):.{cifras}g}"
    if "e" in texto:
        mant, exp = texto.split("e")
        return f"{mant}e{int(exp)}"
    return texto


def tabla_conversiones(valor: F, magnitud: str, de: str) -> list[tuple[str, str]]:
    """Valor convertido a todas las unidades de la magnitud (para la vista de tabla)."""
    return [(f"{u.nombre} ({s})", formatear(convertir(valor, magnitud, de, s)))
            for s, u in MAGNITUDES[magnitud].items()]
