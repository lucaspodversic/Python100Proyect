"""CLI: organizador [CARPETA] [--vigilar] [--simular] [--reglas reglas.json] [--deshacer]."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Sequence

from .motor import Organizador
from .reglas import REGLAS_POR_DEFECTO, Regla


def ejecutar(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="organizador")
    # Carpeta opcional: por defecto ~/Downloads.
    p.add_argument("carpeta", nargs="?", type=Path, default=Path.home() / "Downloads")
    p.add_argument("--vigilar", action="store_true")
    # Segundos entre escaneos en modo --vigilar.
    p.add_argument("--intervalo", type=float, default=5.0)
    p.add_argument("--simular", action="store_true", help="Mostrar qué haría sin mover nada")
    p.add_argument("--reglas", type=Path, help="JSON con lista de reglas personalizadas")
    p.add_argument("--deshacer", action="store_true")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # Caso borde: carpeta inexistente → exit 1 sin crear nada.
    if not a.carpeta.is_dir():
        print(f"No existe la carpeta {a.carpeta}", file=sys.stderr); return 1
    # Reglas desde JSON (lista de objetos {carpeta, extensiones, patron}) o las de fábrica.
    reglas = tuple(Regla.desde_dict(d) for d in json.loads(a.reglas.read_text())) if a.reglas else REGLAS_POR_DEFECTO
    # El historial se guarda dentro de la misma carpeta, oculto con un "." inicial.
    org = Organizador(a.carpeta, reglas, simulacion=a.simular, registro=a.carpeta / ".organizador.json")
    # Modos excluyentes: deshacer la última pasada, vigilar en bucle o una sola pasada.
    if a.deshacer:
        print(f"Revertidos: {len(org.deshacer())}")
    elif a.vigilar:
        try:
            org.vigilar(a.intervalo)
        # Ctrl+C es la forma normal de detener la vigilancia: se sale limpio, sin traceback.
        except KeyboardInterrupt:
            print("\nDetenido.")
    else:
        print(f"{'Se moverían' if a.simular else 'Movidos'}: {len(org.organizar())}")
    return 0


def main() -> None:
    sys.exit(ejecutar())
