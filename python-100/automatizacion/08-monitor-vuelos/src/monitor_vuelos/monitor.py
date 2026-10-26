"""Reglas de alerta (puras) y el monitor que las orquesta."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from .historial import Historial
from .modelos import Cotizacion, Seguimiento
from .notificadores import Notificador
from .proveedores import ProveedorVuelos


@dataclass(frozen=True)
class Alerta:
    seguimiento: Seguimiento
    cotizacion: Cotizacion
    motivo: str

    def mensaje(self) -> str:
        s, c = self.seguimiento, self.cotizacion
        return (f"{s.origen}→{s.destino} {s.fecha}: {c.moneda} {c.precio:.2f} ({c.vuelo}, {c.aerolinea}) — {self.motivo}")


def evaluar_alerta(s: Seguimiento, mejor: Cotizacion, minimo_previo: float | None,
                   ultima_alerta: float | None) -> str | None:
    """Devuelve el motivo de alerta o ``None``.

    Reglas:
    1. Precio <= umbral.
    2. Caída >= ``caida_pct`` respecto del mínimo previo.
    Anti-spam: si ya se alertó, sólo se vuelve a alertar si el precio es
    ESTRICTAMENTE menor al último alertado.
    """
    # Anti-spam primero: si ya avisamos a 880, otra lectura de 880 (o más) no vuelve a notificar.
    if ultima_alerta is not None and mejor.precio >= ultima_alerta:
        return None
    # Regla 1 (umbral absoluto, inclusivo: 900 con umbral 900 alerta).
    if mejor.precio <= s.umbral:
        return f"bajo el umbral de {s.umbral:.2f}"
    # Regla 2 (caída relativa): con 10% y mínimo previo 1200, alerta si precio <= 1080.
    # Requiere historial: sin mínimo previo (primera lectura) no se puede evaluar.
    if s.caida_pct and minimo_previo and mejor.precio <= minimo_previo * (1 - s.caida_pct / 100):
        caida = (1 - mejor.precio / minimo_previo) * 100
        return f"bajó {caida:.1f}% respecto del mínimo previo ({minimo_previo:.2f})"
    return None


@dataclass
class Monitor:
    proveedor: ProveedorVuelos
    notificador: Notificador
    historial: Historial
    reloj: Callable[[], float] = time.time

    def revisar(self, seguimientos: list[Seguimiento]) -> list[Alerta]:
        alertas: list[Alerta] = []
        for s in seguimientos:
            cotizaciones = self.proveedor.buscar(s)
            if not cotizaciones:
                continue
            # Sólo importa la oferta más barata de cada consulta.
            mejor = min(cotizaciones, key=lambda c: c.precio)
            ahora = self.reloj()
            # Orden importante: se lee el mínimo previo ANTES de registrar la lectura actual.
            previo = self.historial.minimo_previo(s.clave, ahora)
            self.historial.registrar(s.clave, mejor.precio, mejor.moneda, mejor.vuelo, ahora)
            motivo = evaluar_alerta(s, mejor, previo, self.historial.ultima_alerta(s.clave))
            if motivo:
                alerta = Alerta(s, mejor, motivo)
                self.notificador.notificar(alerta.mensaje())
                self.historial.guardar_alerta(s.clave, mejor.precio, ahora)
                alertas.append(alerta)
        return alertas

    def vigilar(self, seguimientos: list[Seguimiento], intervalo: float, veces: int,
                dormir: Callable[[float], None] = time.sleep) -> list[Alerta]:
        todas: list[Alerta] = []
        for i in range(veces):
            todas += self.revisar(seguimientos)
            # No se duerme después de la última revisión: con N revisiones hay N-1 esperas.
            if i < veces - 1:
                dormir(intervalo)
        return todas
