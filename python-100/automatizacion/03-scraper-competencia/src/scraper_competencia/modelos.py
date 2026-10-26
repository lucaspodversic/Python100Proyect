"""Modelos de datos del scraper."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class ReglasSitio:
    """Selectores CSS que describen cómo leer el catálogo de un sitio.

    Separar los selectores de la lógica permite agregar competidores con
    sólo un archivo de configuración, sin tocar código.
    """

    # ``nombre`` identifica al competidor en la columna "competidor" del reporte.
    nombre: str
    tarjeta: str  # selector del contenedor de cada producto
    titulo: str
    precio: str
    sku: str | None = None
    enlace: str | None = None
    # Selectores de características extra: nombre de columna -> selector.
    extras: dict[str, str] = field(default_factory=dict)
    siguiente: str | None = None  # selector del link "página siguiente"


@dataclass
class Producto:
    """Producto extraído de una página de la competencia."""

    competidor: str
    titulo: str
    # None cuando el sitio no publica el precio ("Consultar"); Decimal para no perder centavos.
    precio: Decimal | None
    sku: str | None = None
    url: str | None = None
    extras: dict[str, str] = field(default_factory=dict)
