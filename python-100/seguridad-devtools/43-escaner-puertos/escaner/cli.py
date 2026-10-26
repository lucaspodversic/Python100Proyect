"""CLI del escáner. Requiere --host y --autorizado explícitos."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .nucleo import EstadoPuerto, escanear, parsear_puertos

# Texto legal/ético que se muestra en la ayuda y cuando falta --autorizado.
AVISO = ("Sólo escaneá hosts propios o con autorización por escrito. "
         "Usá --autorizado para confirmar que la tenés.")


def ejecutar(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="escaner", description="Escáner TCP para auditar hosts propios. " + AVISO)
    # required=True y sin default: es imposible escanear algo "por accidente".
    p.add_argument("--host", required=True, help="Host a auditar (obligatorio, sin valor por defecto)")
    # Por defecto los puertos "bien conocidos" (1-1024).
    p.add_argument("--puertos", default="1-1024")
    # 50 hilos: rápido sin saturar el host ni la red propia.
    p.add_argument("--hilos", type=int, default=50)
    # 0,5 s por puerto: suficiente en LAN; en redes lentas conviene subirlo.
    p.add_argument("--timeout", type=float, default=0.5)
    p.add_argument("--banner", action="store_true", help="Intentar leer el banner del servicio")
    p.add_argument("--todos", action="store_true", help="Mostrar también cerrados/filtrados")
    p.add_argument("--json", action="store_true")
    # Confirmación explícita: el usuario declara tener permiso sobre el host.
    p.add_argument("--autorizado", action="store_true", help="Confirmo que tengo autorización")
    args = p.parse_args(argv)
    # Sin confirmación no se abre ni un socket: exit 3 (distinto de errores de uso de argparse, que es 2).
    if not args.autorizado:
        print(AVISO, file=sys.stderr)
        return 3
    res = escanear(args.host, parsear_puertos(args.puertos), args.hilos, args.timeout, args.banner)
    # Por defecto sólo interesan los abiertos; --todos muestra también cerrados/filtrados.
    if not args.todos:
        res = [r for r in res if r.estado is EstadoPuerto.ABIERTO]
    # Salida JSON para integrarla con otras herramientas; ensure_ascii=False conserva tildes en banners.
    if args.json:
        print(json.dumps([{"puerto": r.puerto, "estado": r.estado.value, "servicio": r.servicio,
                           "banner": r.banner} for r in res], ensure_ascii=False))
    else:
        for r in res:
            # Columnas alineadas al estilo de nmap: puerto/protocolo, estado, servicio, banner.
            print(f"{r.puerto:>5}/tcp  {r.estado.value:<9} {r.servicio:<9} {r.banner}")
    return 0


def main() -> None:
    sys.exit(ejecutar())
