"""Modelo de vuelo y normalización de textos típicos ("US$ 1.234,50", "2h 35m", "PT2H35M")."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation

# Símbolo o código que aparece en el texto → código ISO 4217.
# "$" solo se asume USD (ambiguo en Latinoamérica: si importa, el perfil fija la moneda).
_MONEDAS = {"US$": "USD", "U$S": "USD", "USD": "USD", "€": "EUR", "EUR": "EUR", "£": "GBP",
            "ARS": "ARS", "MXN": "MXN", "$": "USD"}


@dataclass(frozen=True)
class Vuelo:
    """Una oferta normalizada. Precio en Decimal: con dinero no se usan floats."""

    aerolinea: str
    numero: str
    origen: str         # código IATA en mayúsculas
    destino: str
    salida: datetime    # hora local del aeropuerto, tal como la publica la fuente
    llegada: datetime
    escalas: int
    precio: Decimal
    moneda: str

    @property
    def duracion_min(self) -> int:
        """Duración en minutos (resta directa: asume que salida y llegada están en la misma zona)."""
        return int((self.llegada - self.salida).total_seconds() // 60)

    @property
    def clave(self) -> str:
        """Identifica el vuelo (mismo número y salida) para seguir su precio en el tiempo."""
        return f"{self.numero}@{self.salida:%Y-%m-%dT%H:%M}"


def parsear_precio(texto: str) -> tuple[Decimal, str]:
    """Detecta moneda y separadores decimales en formato latino o anglosajón."""
    t = texto.strip()
    # Se prueban los símbolos de más largo a más corto: si no, "US$ 10" matchearía "$" antes que "US$".
    moneda = next((iso for simb, iso in sorted(_MONEDAS.items(), key=lambda x: -len(x[0])) if simb in t), "")
    # Sólo dígitos y separadores; el resto (símbolos, espacios, NBSP) se descarta.
    num = re.sub(r"[^\d.,]", "", t)
    if not num:
        raise ValueError(f"Sin número en {texto!r}")
    if "," in num and "." in num:
        # Ambos separadores: el que aparece último es el decimal.
        # "1.234,50" → 1234.50 (latino) · "1,234.50" → 1234.50 (anglosajón).
        num = num.replace(".", "").replace(",", ".") if num.rfind(",") > num.rfind(".") else num.replace(",", "")
    elif "," in num:
        # Sólo coma: 1-2 dígitos detrás = decimal ("210,5"); 3 = miles ("1,234").
        partes = num.split(",")
        num = num.replace(",", ".") if len(partes[-1]) in (1, 2) else num.replace(",", "")
    elif num.count(".") > 1 or (num.count(".") == 1 and len(num.split(".")[-1]) == 3):
        # Sólo punto: varios puntos o exactamente 3 dígitos detrás = separador de miles.
        num = num.replace(".", "")               # "1.234" = mil doscientos…
    # (un único punto con 1-2 decimales, "199.90", se deja tal cual)
    try:
        return Decimal(num), moneda
    except InvalidOperation as exc:
        # Caso borde: sólo separadores (",.") no es un número.
        raise ValueError(f"Precio inválido {texto!r}") from exc


def parsear_duracion(texto: str) -> int:
    """'2h 35m', '2 h 5 min', '95 min', 'PT2H35M' → minutos."""
    t = texto.upper()
    h = re.search(r"(\d+)\s*H", t)
    # Los minutos se buscan DESPUÉS de la H: en "PT2H35M" la "M" no se confunde con nada previo.
    m = re.search(r"(\d+)\s*M", t.split("H")[-1] if h else t)
    if not h and not m:
        raise ValueError(f"Duración inválida {texto!r}")
    # Cualquiera de las dos partes puede faltar ("3h", "95 min").
    return int(h.group(1) if h else 0) * 60 + int(m.group(1) if m else 0)


def parsear_escalas(texto: str) -> int:
    """'Directo' / 'Nonstop' / 'sin escalas' → 0; '1 escala', '2 stops' → el número."""
    t = texto.lower()
    if "directo" in t or "nonstop" in t or "sin escala" in t:
        return 0
    n = re.search(r"\d+", t)
    # Texto sin número reconocible: se asume directo (0) en vez de fallar.
    return int(n.group()) if n else 0
