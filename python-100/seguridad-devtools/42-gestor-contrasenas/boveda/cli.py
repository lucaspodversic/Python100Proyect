"""CLI: boveda {init,add,get,list,rm} --archivo RUTA.

La contraseña maestra se pide con getpass o se lee de la variable de
entorno BOVEDA_MAESTRA (útil para scripts; menos seguro).
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path
from typing import Sequence

from .boveda import Boveda, Entrada, generar_contrasena
from .cripto import N_POR_DEFECTO, ErrorDescifrado


def _maestra() -> str:
    # La variable de entorno tiene prioridad (scripts/tests); si no está, se pregunta sin eco.
    return os.environ.get("BOVEDA_MAESTRA") or getpass.getpass("Contraseña maestra: ")


def ejecutar(argv: Sequence[str] | None = None, n_kdf: int = N_POR_DEFECTO) -> int:
    """Ejecuta la CLI. `n_kdf` permite bajar el costo de scrypt en tests."""
    p = argparse.ArgumentParser(prog="boveda")
    # Por defecto en el home del usuario; con --archivo se pueden tener varias bóvedas.
    p.add_argument("--archivo", default=str(Path.home() / ".boveda.bin"))
    # Un subcomando por operación; required=True exige elegir uno.
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    a = sub.add_parser("add")
    a.add_argument("servicio"); a.add_argument("usuario")
    # Sin --generar la contraseña a guardar se pide con getpass (no queda en el historial).
    a.add_argument("--generar", type=int, metavar="LARGO", help="Generar contraseña aleatoria")
    g = sub.add_parser("get"); g.add_argument("servicio")
    sub.add_parser("list")
    r = sub.add_parser("rm"); r.add_argument("servicio")
    args = p.parse_args(argv)
    ruta = Path(args.archivo)
    try:
        # init no abre nada: crea la bóveda y termina.
        if args.cmd == "init":
            Boveda.crear(ruta, _maestra(), n_kdf); print(f"Bóveda creada en {ruta}"); return 0
        # El resto de los comandos necesitan la bóveda abierta (y la maestra correcta).
        b = Boveda.abrir(ruta, _maestra(), n_kdf)
        if args.cmd == "add":
            pwd = generar_contrasena(args.generar) if args.generar else getpass.getpass("Contraseña a guardar: ")
            b.agregar(Entrada(args.servicio, args.usuario, pwd)); b.guardar(); print("Guardada.")
        elif args.cmd == "get":
            # Salida separada por tabulador: fácil de procesar con cut/awk.
            e = b.obtener(args.servicio); print(f"{e.usuario}\t{e.contrasena}")
        elif args.cmd == "list":
            # Orden alfabético para que el listado sea estable.
            for e in sorted(b.entradas.values(), key=lambda x: x.servicio):
                print(f"{e.servicio}\t{e.usuario}")  # no mostramos contraseñas en el listado
        elif args.cmd == "rm":
            b.eliminar(args.servicio); b.guardar(); print("Eliminada.")
        return 0
    # Exit 2 = maestra incorrecta o archivo alterado (distinto de un error de uso).
    except ErrorDescifrado as exc:
        print(f"Error: {exc}", file=sys.stderr); return 2
    # Exit 1 = errores de uso: servicio inexistente/duplicado, bóveda ya creada o inexistente, maestra corta.
    except (KeyError, FileExistsError, FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr); return 1


def main() -> None:
    sys.exit(ejecutar())
