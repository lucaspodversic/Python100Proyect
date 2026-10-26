"""Reglas de alerta.

- Variación respecto de la última lectura guardada (umbral en %).
- Cruce de precio (por encima / por debajo de un valor).
- Variación de 24 h informada por la API.
Lógica pura: recibe la cotización nueva y la anterior, devuelve alertas.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .api import Cotizacion


@dataclass(frozen=True)
class Alerta:
    """Un aviso para una moneda, con su mensaje ya formateado."""
    moneda: str
    mensaje: str


@dataclass(frozen=True)
class ReglaVariacion:
    """Umbrales configurables; los que valen None no se evalúan."""
    # % de cambio respecto de la última lectura guardada.
    umbral_pct: float = 5.0
    # Avisar al cruzar hacia arriba / hacia abajo estos precios.
    precio_mayor: float | None = None
    precio_menor: float | None = None
    # % de cambio en 24 h informado por la API.
    umbral_24h: float | None = None


def variacion_pct(anterior: float, actual: float) -> float:
    """Cambio porcentual de `anterior` a `actual` (0 si no hay precio anterior)."""
    return (actual - anterior) / anterior * 100 if anterior else 0.0


def evaluar(nueva: Cotizacion, anterior: Cotizacion | None, regla: ReglaVariacion) -> list[Alerta]:
    """Devuelve las alertas que dispara la cotización nueva frente a la anterior."""
    alertas = []
    # Sin lectura previa (primera ejecución) no se puede calcular la variación.
    if anterior:
        v = variacion_pct(anterior.precio, nueva.precio)
        # abs(): se avisa tanto en subidas como en bajadas.
        if abs(v) >= regla.umbral_pct:
            flecha = "▲" if v > 0 else "▼"
            # :g muestra el precio sin ceros sobrantes (60000 en vez de 60000.000000).
            alertas.append(Alerta(nueva.moneda, f"{flecha} {nueva.moneda} {v:+.2f}% desde la última lectura "
                                                f"({anterior.precio:g} → {nueva.precio:g} {nueva.divisa})"))
    # Cruces: sólo avisan al cruzar (no en cada lectura mientras siga arriba)
    if regla.precio_mayor is not None and nueva.precio >= regla.precio_mayor and \
            (anterior is None or anterior.precio < regla.precio_mayor):
        alertas.append(Alerta(nueva.moneda, f"{nueva.moneda} superó {regla.precio_mayor:g} {nueva.divisa}"))
    if regla.precio_menor is not None and nueva.precio <= regla.precio_menor and \
            (anterior is None or anterior.precio > regla.precio_menor):
        alertas.append(Alerta(nueva.moneda, f"{nueva.moneda} bajó de {regla.precio_menor:g} {nueva.divisa}"))
    # La API puede no informar el cambio de 24 h (None): en ese caso no se evalúa.
    if regla.umbral_24h is not None and nueva.cambio_24h is not None and abs(nueva.cambio_24h) >= regla.umbral_24h:
        alertas.append(Alerta(nueva.moneda, f"{nueva.moneda} {nueva.cambio_24h:+.2f}% en 24 h"))
    return alertas


# Interfaz para enviar alertas: consola hoy; mañana mail, Telegram, etc.
class Notificador(Protocol):
    def enviar(self, alerta: Alerta) -> None: ...


class NotificadorConsola:
    """Imprime cada alerta con una campanita; `escribir` es inyectable."""
    def __init__(self, escribir=print) -> None:
        self.escribir = escribir

    def enviar(self, alerta: Alerta) -> None:
        self.escribir(f"🔔 {alerta.mensaje}")
