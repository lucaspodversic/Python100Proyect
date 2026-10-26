"""Historial de cotizaciones en CSV (fácil de abrir en una planilla)."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from .api import Cotizacion

# Encabezado del CSV, en el orden de las columnas.
CAMPOS = ["momento", "moneda", "divisa", "precio", "cambio_24h"]


class Historial:
    """Agrega y lee cotizaciones en un CSV que crece con cada lectura."""
    def __init__(self, ruta: Path) -> None:
        self.ruta = Path(ruta)

    def agregar(self, cotizaciones: list[Cotizacion]) -> None:
        # El encabezado se escribe sólo al crear el archivo.
        nuevo = not self.ruta.exists()
        # Modo "a" (append): nunca se pierden lecturas anteriores. newline="" lo pide el módulo csv.
        with self.ruta.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if nuevo:
                w.writerow(CAMPOS)
            for c in cotizaciones:
                w.writerow([c.momento.isoformat(), c.moneda, c.divisa, c.precio,
                            # None se guarda como celda vacía.
                            "" if c.cambio_24h is None else c.cambio_24h])

    def leer(self) -> list[Cotizacion]:
        if not self.ruta.exists():
            return []
        with self.ruta.open(encoding="utf-8") as f:
            # Se reconstruyen los tipos: precio float, celda vacía → None, fecha ISO → datetime.
            return [Cotizacion(r["moneda"], float(r["precio"]), r["divisa"],
                               float(r["cambio_24h"]) if r["cambio_24h"] else None,
                               datetime.fromisoformat(r["momento"])) for r in csv.DictReader(f)]

    def ultima(self, moneda: str, divisa: str) -> Cotizacion | None:
        # Se lee todo el archivo: suficiente para un historial personal.
        previas = [c for c in self.leer() if c.moneda == moneda and c.divisa == divisa]
        # La última fila es la lectura más reciente.
        return previas[-1] if previas else None
