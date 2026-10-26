"""Modelo normalizado de una oferta y parseo de salarios en texto libre."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Oferta:
    """Oferta de empleo normalizada, igual venga de JSON-LD o de HTML."""
    titulo: str
    empresa: str
    ubicacion: str = ""
    url: str = ""
    salario_min: float | None = None
    salario_max: float | None = None
    moneda: str = ""
    remoto: bool = False
    fecha: str = ""
    etiquetas: tuple[str, ...] = field(default_factory=tuple)

    @property
    def clave(self) -> str:
        """Identificador para deduplicar: URL si hay, si no título+empresa+ubicación."""
        base = self.url or f"{self.titulo}|{self.empresa}|{self.ubicacion}".lower()
        # SHA-1 sólo como huella para deduplicar (no es un uso de seguridad); 12 hex alcanzan.
        return hashlib.sha1(base.encode()).hexdigest()[:12]


# Se recorren en orden de inserción: los símbolos más específicos ("us$", "u$s") antes que "$" solo.
_MONEDAS = {"€": "EUR", "eur": "EUR", "us$": "USD", "usd": "USD", "u$s": "USD", "$": "ARS", "ars": "ARS"}
# Número con miles separados por punto o espacio (40.000 / 40 000) o con decimal (2,5), y sufijo k/mil opcional.
_NUM = r"(\d{1,3}(?:[.\s]\d{3})+|\d+(?:[.,]\d+)?)\s*(k|mil)?"


def _a_numero(txt: str, sufijo: str | None) -> float:
    """Convierte el texto numérico a float aplicando el multiplicador k/mil."""
    if re.fullmatch(r"\d{1,3}(?:[.\s]\d{3})+", txt):
        valor = float(re.sub(r"[.\s]", "", txt))   # separador de miles
    else:
        # Coma decimal → punto.
        valor = float(txt.replace(",", "."))
    return valor * 1000 if sufijo else valor


def parsear_salario(texto: str) -> tuple[float | None, float | None, str]:
    """'30.000 - 40.000 €' → (30000, 40000, 'EUR'); '45k USD' → (45000, 45000, 'USD')."""
    t = texto.lower()
    moneda = ""
    for simbolo, cod in _MONEDAS.items():  # el orden importa: 'us$' antes que '$'
        if simbolo in t:
            moneda = cod
            break
    # Todos los números del texto, con su sufijo.
    nums = [_a_numero(n, s) for n, s in re.findall(_NUM, t)]
    # Caso borde: "A convenir" → sin salario, pero se conserva la moneda si se detectó.
    if not nums:
        return None, None, moneda
    # Sólo los dos primeros números (un rango); con uno solo, mínimo = máximo.
    return min(nums[:2]), max(nums[:2]), moneda
