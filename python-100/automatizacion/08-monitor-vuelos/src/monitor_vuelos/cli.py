"""CLI::

    export AMADEUS_CLIENT_ID=... AMADEUS_CLIENT_SECRET=...
    monitor-vuelos EZE MAD 2025-03-10 --umbral 900 --caida 10 --cada 3600 --veces 24
    monitor-vuelos EZE MAD 2025-03-10 --umbral 900 --demo     # proveedor simulado
"""

from __future__ import annotations

import argparse
import os
import time

from .historial import Historial
from .modelos import Seguimiento
from .monitor import Monitor
from .notificadores import ConsolaNotificador, Notificador, WebhookNotificador
from .proveedores import AmadeusProveedor, FakeProveedor, ProveedorVuelos


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="monitor-vuelos", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("origen")
    ap.add_argument("destino")
    ap.add_argument("fecha")
    ap.add_argument("--umbral", type=float, required=True)
    # --caida es opcional: sin él sólo se usa la regla del umbral absoluto.
    ap.add_argument("--caida", type=float, default=None, help="% de caída vs mínimo previo")
    ap.add_argument("--adultos", type=int, default=1)
    ap.add_argument("--cada", type=float, default=3600)
    ap.add_argument("--veces", type=int, default=1)
    # Historial persistente por defecto: entre corridas de cron se conserva el mínimo previo.
    ap.add_argument("--historial", default="vuelos.db")
    # La URL del webhook puede venir de una variable de entorno para no dejarla en el crontab.
    ap.add_argument("--webhook", default=os.environ.get("MONITOR_WEBHOOK"))
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args(argv)
    proveedor: ProveedorVuelos
    # Guion demo: mínimos 1100 → 1050 → 880; con umbral 900 sólo el tercero alerta.
    if a.demo:
        proveedor = FakeProveedor([[1200, 1100], [1050], [880, 950]])
    else:  # pragma: no cover - requiere credenciales reales
        # Credenciales sólo desde el entorno (nunca por argumento: quedarían en el historial del shell).
        # Si faltan, KeyError explícito.
        proveedor = AmadeusProveedor(os.environ["AMADEUS_CLIENT_ID"], os.environ["AMADEUS_CLIENT_SECRET"])
    notif: Notificador = WebhookNotificador(a.webhook) if a.webhook else ConsolaNotificador()
    # Códigos IATA normalizados a mayúsculas ("eze" → "EZE"): la API y la clave del historial lo esperan.
    s = Seguimiento(a.origen.upper(), a.destino.upper(), a.fecha, a.umbral, a.adultos, a.caida)
    # En modo demo no esperamos entre revisiones.
    dormir = (lambda _x: None) if a.demo else time.sleep
    alertas = Monitor(proveedor, notif, Historial(a.historial)).vigilar([s], a.cada, a.veces, dormir=dormir)
    print(f"{len(alertas)} alerta(s) emitidas.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
