"""CLI: nuevo, hecho, deshacer, ver, borrar."""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path
from typing import Sequence

from .almacen import Almacen
from .modelo import TODOS_LOS_DIAS, Habito, calendario, estadisticas

# Iniciales de los días en español; X = miércoles (para no chocar con M = martes).
LETRAS = {"l": 0, "m": 1, "x": 2, "j": 3, "v": 4, "s": 5, "d": 6}


def parsear_dias(t: str) -> frozenset[int]:
    """'lmxjv' → lunes a viernes; 'todos' → los 7 días."""
    if t == "todos":
        return TODOS_LOS_DIAS
    try:
        # Una letra desconocida lanza KeyError, que se traduce a un mensaje claro.
        return frozenset(LETRAS[c] for c in t.lower())
    except KeyError:
        raise ValueError("Días: usá letras L M X J V S D, p. ej. 'lmv'") from None


# `hoy` y `archivo` inyectables para tests deterministas.
def ejecutar(argv: Sequence[str] | None = None, hoy: date | None = None, archivo: Path | None = None) -> int:
    hoy = hoy or date.today()
    p = argparse.ArgumentParser(prog="habitos")
    # Prioridad: --archivo > parámetro `archivo` > variable HABITOS_ARCHIVO > ~/.habitos.json.
    p.add_argument("--archivo", type=Path,
                   default=archivo or Path(os.environ.get("HABITOS_ARCHIVO", Path.home() / ".habitos.json")))
    sub = p.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("nuevo"); n.add_argument("nombre"); n.add_argument("--dias", default="todos")
    # hecho y deshacer aceptan --fecha para corregir días pasados.
    for c in ("hecho", "deshacer"):
        s = sub.add_parser(c); s.add_argument("nombre"); s.add_argument("--fecha", type=date.fromisoformat)
    # `ver` sin nombre muestra todos los hábitos.
    v = sub.add_parser("ver"); v.add_argument("nombre", nargs="?"); v.add_argument("--semanas", type=int, default=4)
    b = sub.add_parser("borrar"); b.add_argument("nombre")
    a = p.parse_args(argv)
    alm = Almacen(a.archivo)
    hs = alm.cargar()
    try:
        if a.cmd == "nuevo":
            # Caso borde: no se pisa un hábito existente.
            if a.nombre in hs:
                raise ValueError(f"Ya existe «{a.nombre}»")
            hs[a.nombre] = Habito(a.nombre, hoy, parsear_dias(a.dias))
            print(f"Creado «{a.nombre}»")
        # Validación común para los comandos que necesitan un hábito existente.
        elif a.cmd in ("hecho", "deshacer", "borrar") and a.nombre not in hs:
            raise ValueError(f"No existe «{a.nombre}»")
        elif a.cmd == "hecho":
            hs[a.nombre].marcar(a.fecha or hoy)
            print(f"✔ {a.nombre} — racha: {estadisticas(hs[a.nombre], hoy).racha_actual}")
        elif a.cmd == "deshacer":
            hs[a.nombre].desmarcar(a.fecha or hoy)
        elif a.cmd == "borrar":
            del hs[a.nombre]
        elif a.cmd == "ver":
            elegidos = [hs[a.nombre]] if a.nombre else list(hs.values())
            for h in elegidos:
                # Resumen en una línea y debajo el calendario de las últimas semanas.
                e = estadisticas(h, hoy)
                print(f"{h.nombre}: racha {e.racha_actual} (mejor {e.mejor_racha}) · "
                      f"{e.cumplimiento:.0%} últimos 30 días · {e.total} en total")
                print(calendario(h, hoy, a.semanas))
            if not elegidos:
                print("Todavía no hay hábitos. Creá uno con: habitos nuevo <nombre>")
    # Ante un error se sale sin guardar: el archivo queda como estaba.
    except (ValueError, KeyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    # Se guarda siempre al final de un comando exitoso (también en `ver`, sin cambios).
    alm.guardar(hs)
    return 0


def main() -> None:
    sys.exit(ejecutar())
