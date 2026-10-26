"""CLI: cripto bitcoin ethereum --divisa eur --umbral 3 [--vigilar 300]."""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Callable, Sequence

from .alertas import Notificador, NotificadorConsola, ReglaVariacion, evaluar
from .api import ApiCoinGecko
from .cliente import BloqueadoPorRobots, ErrorHTTP
from .historial import Historial


def una_pasada(api: ApiCoinGecko, ids: list[str], divisa: str, hist: Historial, regla: ReglaVariacion,
               notif: Notificador, escribir: Callable[[str], None] = print) -> int:
    """Consulta, muestra, evalúa alertas, guarda en el historial; devuelve cuántas alertas hubo."""
    cots = api.precios(ids, divisa)
    n = 0
    for c in cots:
        cambio = "" if c.cambio_24h is None else f" ({c.cambio_24h:+.2f}% 24h)"
        # Columnas alineadas: moneda, precio con separador de miles y divisa.
        escribir(f"{c.moneda:<12} {c.precio:>14,.2f} {c.divisa.upper()}{cambio}")
        # Se compara con la última lectura guardada de esa moneda y divisa.
        for a in evaluar(c, hist.ultima(c.moneda, c.divisa), regla):
            notif.enviar(a); n += 1
    # Se guarda DESPUÉS de evaluar: si no, se compararía la lectura consigo misma.
    hist.agregar(cots)
    # Ids que CoinGecko no devolvió (mal escritos o inexistentes).
    faltantes = set(ids) - {c.moneda for c in cots}
    if faltantes:
        escribir(f"Sin datos para: {', '.join(sorted(faltantes))} (¿id de CoinGecko correcto?)")
    return n


# `api`, `dormir` y `max_iter` inyectables: los tests no esperan ni repiten para siempre.
def ejecutar(argv: Sequence[str] | None = None, api: ApiCoinGecko | None = None,
             dormir: Callable[[float], None] = time.sleep, max_iter: int | None = None) -> int:
    p = argparse.ArgumentParser(prog="cripto")
    p.add_argument("monedas", nargs="+", help="ids de CoinGecko: bitcoin ethereum solana…")
    p.add_argument("--divisa", default="usd")
    # "%%" porque argparse interpreta "%" en los textos de ayuda.
    p.add_argument("--umbral", type=float, default=5.0, help="%% de variación para alertar")
    p.add_argument("--mayor", type=float); p.add_argument("--menor", type=float)
    p.add_argument("--umbral-24h", type=float)
    p.add_argument("--historial", type=Path, default=Path("cripto_historial.csv"))
    p.add_argument("--vigilar", type=float, metavar="SEG", help="repetir cada SEG segundos (mín. 60)")
    a = p.parse_args(argv)
    # La clave se lee de una variable de entorno (nunca se escribe en el código).
    api = api or ApiCoinGecko(clave_api=os.environ.get("COINGECKO_API_KEY"))
    regla = ReglaVariacion(a.umbral, a.mayor, a.menor, a.umbral_24h)
    hist, notif = Historial(a.historial), NotificadorConsola()
    i = 0
    try:
        while True:
            una_pasada(api, a.monedas, a.divisa, hist, regla, notif)
            i += 1
            # Sin --vigilar se hace una sola pasada.
            if not a.vigilar or (max_iter and i >= max_iter):
                return 0
            dormir(max(60.0, a.vigilar))  # no saturar la API gratuita
    # Error de la API, bloqueo por robots.txt, datos inválidos o de red/archivo → exit 1.
    except (ErrorHTTP, BloqueadoPorRobots, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    # Ctrl+C es la forma normal de cortar la vigilancia.
    except KeyboardInterrupt:
        return 0


def main() -> None:
    sys.exit(ejecutar())
