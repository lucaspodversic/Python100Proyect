"""Modelos de dominio."""

from __future__ import annotations

from dataclasses import dataclass


# frozen=True: inmutable y hasheable; un seguimiento no cambia mientras se vigila.
@dataclass(frozen=True)
class Seguimiento:
    """Un vuelo a vigilar: ruta + fecha + umbral de alerta."""

    origen: str  # código IATA, ej. "EZE"
    destino: str  # ej. "MAD"
    fecha: str  # AAAA-MM-DD
    umbral: float  # alertar si el precio <= umbral
    adultos: int = 1
    caida_pct: float | None = None  # alertar también si baja X% vs el mínimo previo

    @property
    def clave(self) -> str:
        """Identificador estable para el historial."""
        # Incluye adultos porque el precio total depende de la cantidad de pasajeros.
        # El umbral NO es parte de la clave: cambiarlo no debe perder el historial.
        return f"{self.origen}-{self.destino}-{self.fecha}-{self.adultos}"


@dataclass(frozen=True)
class Cotizacion:
    """Precio total ofrecido por un proveedor para un itinerario."""

    precio: float
    moneda: str
    aerolinea: str
    vuelo: str
    salida: str  # fecha/hora ISO
