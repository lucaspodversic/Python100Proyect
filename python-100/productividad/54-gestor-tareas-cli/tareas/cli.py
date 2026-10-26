"""CLI con subcomandos: agregar, listar, hecha, editar, borrar, limpiar.

Ejemplo: tareas agregar "Pagar luz" -p alta -v viernes -e casa
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path
from typing import Sequence

from .modelo import Prioridad, Tarea, parsear_fecha
from .repositorio import Repositorio

# Ancho fijo de 3 caracteres para que las columnas queden alineadas.
SIMBOLO = {Prioridad.ALTA: "!!!", Prioridad.MEDIA: "!! ", Prioridad.BAJA: "!  "}


def formatear(t: Tarea, hoy: date) -> str:
    """Una línea por tarea: id, casilla, prioridad, vencimiento, estado, título y #etiquetas."""
    marca = "[x]" if t.hecha else "[ ]"
    # Sin fecha se muestran 10 guiones (mismo ancho que AAAA-MM-DD).
    vence = t.vence.isoformat() if t.vence else "-" * 10
    tags = " ".join(f"#{e}" for e in sorted(t.etiquetas))
    return f"{t.id:>3} {marca} {SIMBOLO[t.prioridad]} {vence} {t.estado(hoy):<9} {t.titulo} {tags}".rstrip()


# `hoy` y `db` inyectables: los tests usan una fecha fija y una base temporal.
def ejecutar(argv: Sequence[str] | None = None, hoy: date | None = None,
             db: str | Path | None = None) -> int:
    hoy = hoy or date.today()
    p = argparse.ArgumentParser(prog="tareas")
    # Prioridad de la base: --db > parámetro `db` > variable TAREAS_DB > ~/.tareas.db.
    p.add_argument("--db", default=db or os.environ.get("TAREAS_DB", Path.home() / ".tareas.db"))
    sub = p.add_subparsers(dest="cmd", required=True)
    # Un subparser por comando; -e se puede repetir para varias etiquetas.
    a = sub.add_parser("agregar"); a.add_argument("titulo")
    a.add_argument("-p", "--prioridad", default="media"); a.add_argument("-v", "--vence")
    a.add_argument("-e", "--etiqueta", action="append", default=[])
    # Por defecto sólo pendientes; --todas incluye las hechas.
    l = sub.add_parser("listar"); l.add_argument("--todas", action="store_true")
    l.add_argument("-e", "--etiqueta"); l.add_argument("-p", "--prioridad")
    l.add_argument("--hasta", help="sólo las que vencen hasta esa fecha")
    h = sub.add_parser("hecha"); h.add_argument("id", type=int)
    # En editar, "-v -" quita la fecha de vencimiento.
    e = sub.add_parser("editar"); e.add_argument("id", type=int); e.add_argument("--titulo")
    e.add_argument("-p", "--prioridad"); e.add_argument("-v", "--vence")
    b = sub.add_parser("borrar"); b.add_argument("id", type=int)
    sub.add_parser("limpiar")
    args = p.parse_args(argv)
    repo = Repositorio(args.db)
    try:
        if args.cmd == "agregar":
            t = repo.agregar(Tarea(args.titulo, Prioridad.desde_texto(args.prioridad),
                                   # Las fechas relativas ("viernes", "+3") se resuelven contra `hoy`.
                                   parsear_fecha(args.vence, hoy) if args.vence else None,
                                   set(args.etiqueta)))
            print(f"Agregada #{t.id}")
        elif args.cmd == "listar":
            ts = repo.listar(incluir_hechas=args.todas, etiqueta=args.etiqueta,
                             # --prioridad en listar actúa como mínimo: "media" muestra media y alta.
                             prioridad_min=Prioridad.desde_texto(args.prioridad) if args.prioridad else None,
                             vencen_hasta=parsear_fecha(args.hasta, hoy) if args.hasta else None)
            for t in ts:
                print(formatear(t, hoy))
            if not ts:
                print("Sin tareas 🎉")
        elif args.cmd == "hecha":
            # obtener lanza KeyError si el id no existe (se informa abajo).
            t = repo.obtener(args.id); t.hecha = True; repo.actualizar(t)
            print(f"Completada #{t.id}")
        elif args.cmd == "editar":
            t = repo.obtener(args.id)
            # Sólo se cambian los campos indicados; el resto queda igual.
            if args.titulo: t.titulo = args.titulo
            if args.prioridad: t.prioridad = Prioridad.desde_texto(args.prioridad)
            if args.vence: t.vence = None if args.vence == "-" else parsear_fecha(args.vence, hoy)
            repo.actualizar(t); print(f"Editada #{t.id}")
        elif args.cmd == "borrar":
            repo.borrar(args.id); print(f"Borrada #{args.id}")
        elif args.cmd == "limpiar":
            print(f"Eliminadas {repo.limpiar_hechas()} tareas hechas")
    # Id inexistente, fecha o prioridad inválida → mensaje limpio (args[0] evita las comillas de KeyError) y exit 1.
    except (KeyError, ValueError) as exc:
        print(f"Error: {exc.args[0]}", file=sys.stderr)
        return 1
    return 0


def main() -> None:
    sys.exit(ejecutar())
