"""CLI: cifrador {cifrar,descifrar} ORIGEN [-o DESTINO]."""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path
from typing import Sequence

from .nucleo import N_POR_DEFECTO, ErrorCifrado, cifrar_archivo, descifrar_archivo


def _pedir(confirmar: bool) -> str:
    """Lee la contraseña (env CIFRADOR_CLAVE o getpass con confirmación)."""
    # Variable de entorno para scripts y tests; interactivamente se pide sin eco.
    if os.environ.get("CIFRADOR_CLAVE"):
        return os.environ["CIFRADOR_CLAVE"]
    c = getpass.getpass("Contraseña: ")
    # Al cifrar se pide dos veces: un error de tipeo dejaría el archivo irrecuperable.
    if confirmar and c != getpass.getpass("Repetir: "):
        raise ValueError("Las contraseñas no coinciden")
    return c


def ejecutar(argv: Sequence[str] | None = None, n: int = N_POR_DEFECTO) -> int:
    p = argparse.ArgumentParser(prog="cifrador")
    p.add_argument("accion", choices=["cifrar", "descifrar"])
    p.add_argument("origen", type=Path)
    # Destino opcional: si falta se deriva del nombre de origen.
    p.add_argument("-o", "--destino", type=Path)
    a = p.parse_args(argv)
    try:
        if a.accion == "cifrar":
            # "foto.jpg" → "foto.jpg.aesf" (se conserva la extensión original dentro del nombre).
            destino = a.destino or a.origen.with_name(a.origen.name + ".aesf")
            cifrar_archivo(a.origen, destino, _pedir(True), n)
        else:
            # "foto.jpg.aesf" → "foto.jpg"; si no termina en .aesf se agrega ".descifrado" para no pisar el origen.
            destino = a.destino or (a.origen.with_suffix("") if a.origen.suffix == ".aesf"
                                    else a.origen.with_name(a.origen.name + ".descifrado"))
            # Al descifrar no hace falta confirmar: una clave mal tipeada simplemente falla la verificación.
            descifrar_archivo(a.origen, destino, _pedir(False))
        print(f"OK → {destino}")
        return 0
    # Exit 2 = clave incorrecta o archivo dañado/manipulado.
    except ErrorCifrado as exc:
        print(f"Error: {exc}", file=sys.stderr); return 2
    # Exit 1 = archivo inexistente, destino ya existente o contraseñas que no coinciden.
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr); return 1


def main() -> None:
    sys.exit(ejecutar())
