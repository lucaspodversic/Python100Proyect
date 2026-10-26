"""Comparación de ofertas e historial de precios con alertas."""
from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path

from .modelo import Vuelo


class Criterio(str, Enum):
    """Criterio de orden. Hereda de str para usarse directo en argparse/JSON."""

    PRECIO = "precio"
    DURACION = "duracion"
    EQUILIBRIO = "equilibrio"   # precio + valor del tiempo


def ordenar(vuelos: list[Vuelo], criterio: Criterio = Criterio.PRECIO, valor_hora: Decimal = Decimal(20)) -> list[Vuelo]:
    """'equilibrio' suma al precio el costo del tiempo de viaje (valor_hora por hora)."""
    # Cada clave es una tupla: el segundo elemento desempata (ej. mismo precio → el más corto).
    claves = {Criterio.PRECIO: lambda v: (v.precio, v.duracion_min),
              Criterio.DURACION: lambda v: (v.duracion_min, v.precio),
              Criterio.EQUILIBRIO: lambda v: (v.precio + valor_hora * Decimal(v.duracion_min) / 60, v.precio)}
    # Criterio(criterio) acepta tanto el enum como su valor en texto ("duracion").
    return sorted(vuelos, key=claves[Criterio(criterio)])


def filtrar(vuelos: list[Vuelo], max_escalas: int | None = None, precio_max: Decimal | None = None,
            salida_desde: int | None = None, salida_hasta: int | None = None) -> list[Vuelo]:
    """salida_desde/hasta son horas del día (0-23), ej. 6 y 12 para vuelos de mañana.

    None = no filtrar por ese criterio. Los límites son inclusivos.
    """
    return [v for v in vuelos
            if (max_escalas is None or v.escalas <= max_escalas)
            and (precio_max is None or v.precio <= precio_max)
            and (salida_desde is None or v.salida.hour >= salida_desde)
            and (salida_hasta is None or v.salida.hour <= salida_hasta)]


def resumen_por_aerolinea(vuelos: list[Vuelo]) -> dict[str, tuple[int, Decimal]]:
    """aerolínea → (cantidad, precio mínimo), ordenado alfabéticamente."""
    g: dict[str, list[Decimal]] = defaultdict(list)
    for v in vuelos:
        g[v.aerolinea].append(v.precio)
    return {a: (len(p), min(p)) for a, p in sorted(g.items())}


@dataclass
class HistorialPrecios:
    """CSV append-only: momento, clave, precio, moneda. Permite detectar bajas."""
    ruta: Path

    def registrar(self, vuelos: list[Vuelo], momento: datetime) -> None:
        """Agrega una fila por vuelo; escribe el encabezado sólo si el archivo es nuevo."""
        nuevo = not Path(self.ruta).exists()
        # Modo "a": nunca se reescribe el historial, sólo se agregan observaciones.
        with Path(self.ruta).open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if nuevo:
                w.writerow(["momento", "clave", "ruta", "precio", "moneda"])
            for v in vuelos:
                w.writerow([momento.isoformat(), v.clave, f"{v.origen}-{v.destino}", v.precio, v.moneda])

    def minimos(self) -> dict[str, Decimal]:
        """Precio mínimo observado por clave de vuelo; {} si todavía no hay historial."""
        if not Path(self.ruta).exists():
            return {}
        res: dict[str, Decimal] = {}
        with Path(self.ruta).open(encoding="utf-8") as f:
            for fila in csv.DictReader(f):
                p = Decimal(fila["precio"])
                # Primera vez que aparece la clave: el default `p` hace que min(p, p) = p.
                res[fila["clave"]] = min(p, res.get(fila["clave"], p))
        return res

    def bajas(self, vuelos: list[Vuelo]) -> list[tuple[Vuelo, Decimal]]:
        """Vuelos cuyo precio actual es menor al mínimo histórico (antes de registrar).

        Vuelos nunca vistos no cuentan como baja (no hay con qué comparar).
        No convierte monedas: se asume que un mismo vuelo se cotiza siempre en la misma.
        """
        m = self.minimos()
        return [(v, m[v.clave]) for v in vuelos if v.clave in m and v.precio < m[v.clave]]
