"""CLI: venvctl {crear,listar,eliminar,activar,instalar,congelar,info}."""
from __future__ import annotations

import argparse
import subprocess
import sys
from typing import Sequence

from .gestor import ErrorGestor, Gestor


# `gestor` es inyectable: los tests pasan uno con ejecutor y creador falsos.
def ejecutar(argv: Sequence[str] | None = None, gestor: Gestor | None = None) -> int:
    p = argparse.ArgumentParser(prog="venvctl")
    # Un subcomando por operación del gestor.
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("crear"); c.add_argument("nombre"); c.add_argument("paquetes", nargs="*")
    # Sin pip la creación es mucho más rápida (útil si sólo se quiere un intérprete aislado).
    c.add_argument("--sin-pip", action="store_true")
    sub.add_parser("listar")
    # -y omite la confirmación interactiva (para scripts).
    e = sub.add_parser("eliminar"); e.add_argument("nombre"); e.add_argument("-y", action="store_true")
    a = sub.add_parser("activar"); a.add_argument("nombre")
    # Cada shell activa el entorno con un script distinto.
    a.add_argument("--shell", default="bash", choices=["bash", "zsh", "fish", "powershell", "cmd"])
    i = sub.add_parser("instalar"); i.add_argument("nombre"); i.add_argument("paquetes", nargs="+")
    f = sub.add_parser("congelar"); f.add_argument("nombre")
    n = sub.add_parser("info"); n.add_argument("nombre")
    args = p.parse_args(argv)
    # Sin gestor inyectado se usa la carpeta real (~/.venvctl o VENVCTL_HOME).
    g = gestor or Gestor()
    try:
        if args.cmd == "crear":
            print(f"Creado: {g.crear(args.nombre, args.paquetes, not args.sin_pip)}")
        elif args.cmd == "listar":
            for nom in g.listar():
                print(nom)
        elif args.cmd == "eliminar":
            # Borrar es irreversible: se pide confirmación salvo -y; sólo "s" confirma.
            if not args.y and input(f"¿Eliminar {args.nombre}? [s/N] ").strip().lower() != "s":
                print("Cancelado."); return 0
            g.eliminar(args.nombre); print("Eliminado.")
        elif args.cmd == "activar":
            print(g.comando_activar(args.nombre, args.shell))
        elif args.cmd == "instalar":
            print(g.instalar(args.nombre, args.paquetes))
        elif args.cmd == "congelar":
            # end="": la salida de pip freeze ya termina en salto de línea.
            print(g.congelar(args.nombre), end="")
        elif args.cmd == "info":
            inf = g.info(args.nombre)
            # Tamaño en MB decimales (1e6 bytes) con un decimal.
            print(f"{inf.nombre}\nRuta: {inf.ruta}\nPython: {inf.version_python}\nTamaño: {inf.tamano_bytes / 1e6:.1f} MB")
        return 0
    # Errores de uso o de pip (exit != 0 del subproceso) → mensaje y exit 1.
    except (ErrorGestor, subprocess.CalledProcessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def main() -> None:
    sys.exit(ejecutar())
