"""CLI: clima "Córdoba" [--dias 7] | [--desde 2026-01-01 --hasta 2026-01-31] [--csv salida.csv]"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Sequence

from .analisis import estadisticas, grafico_ascii, guardar_csv
from .api import ApiOpenMeteo
from .cliente import BloqueadoPorRobots, ErrorHTTP


def ejecutar(argv: Sequence[str] | None = None, api: ApiOpenMeteo | None = None) -> int:
    """Exit codes: 0 ok, 1 dato inválido / ciudad inexistente, 2 error de red o de la API."""
    p = argparse.ArgumentParser(prog="clima")
    p.add_argument("ciudades", nargs="+")
    p.add_argument("--dias", type=int, default=7)
    # type=date.fromisoformat: argparse valida el formato AAAA-MM-DD y da un error claro.
    p.add_argument("--desde", type=date.fromisoformat); p.add_argument("--hasta", type=date.fromisoformat)
    p.add_argument("--csv", type=Path, help="carpeta o archivo .csv")
    a = p.parse_args(argv)
    # Modo histórico requiere ambas fechas: una sola es ambigua.
    if bool(a.desde) != bool(a.hasta):
        p.error("--desde y --hasta van juntos")
    api = api or ApiOpenMeteo()
    try:
        for ciudad in a.ciudades:
            lugar = api.buscar_lugar(ciudad)
            dias = api.historico(lugar, a.desde, a.hasta) if a.desde else api.pronostico(lugar, a.dias)
            e = estadisticas(dias)
            # Se muestran país y coordenadas para que el usuario verifique que es la ciudad correcta.
            print(f"\n== {lugar.nombre}, {lugar.pais} ({lugar.latitud:.2f}, {lugar.longitud:.2f}) ==")
            print(grafico_ascii(dias))
            print(f"Máx. media {e.t_max_media}°C · Mín. media {e.t_min_media}°C · "
                  f"Lluvia {e.lluvia_total} mm en {e.dias_lluvia} día(s)")
            if a.csv:
                # Un .csv con una sola ciudad → ese archivo. En otro caso --csv es una carpeta
                # (se crea; mkdir devuelve None, por eso el `or`) con un archivo por ciudad.
                destino = a.csv if a.csv.suffix == ".csv" and len(a.ciudades) == 1 else \
                    (a.csv.mkdir(parents=True, exist_ok=True) or a.csv / f"{lugar.nombre}.csv")
                print(f"CSV: {guardar_csv(lugar, dias, destino)}")
    except (LookupError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr); return 1
    except (ErrorHTTP, BloqueadoPorRobots, OSError) as exc:
        print(f"Error de red: {exc}", file=sys.stderr); return 2
    return 0


def main() -> None:
    sys.exit(ejecutar())
