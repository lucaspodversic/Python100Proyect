"""CLI: ``informes-pdf --db ventas.db --desde 2024-01-01 --hasta 2024-12-31 -o informe.pdf``.

``--demo`` usa una base en memoria con datos sintéticos.
``--cada-dia HH:MM`` deja el proceso corriendo y genera el informe a diario.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
from pathlib import Path

from .datos import Repositorio, crear_base_demo
from .informe import generar_informe
from .programador import Programacion, ejecutar_programado


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="informes-pdf", description=__doc__)
    # Sin --db (o con --demo) se trabaja con una base en memoria cargada con datos sintéticos.
    ap.add_argument("--db", default=None, help="ruta a la base SQLite")
    ap.add_argument("--demo", action="store_true")
    # Fechas en formato ISO como texto: en SQLite se comparan bien con BETWEEN porque el
    # orden alfabético de "AAAA-MM-DD" coincide con el orden cronológico.
    ap.add_argument("--desde", default="2024-01-01")
    ap.add_argument("--hasta", default="2024-12-31")
    ap.add_argument("-o", "--salida", type=Path, default=Path("informe.pdf"))
    ap.add_argument("--cada-dia", default=None, metavar="HH:MM")
    a = ap.parse_args(argv)
    # Una única conexión para todo el proceso; en modo programado se reutiliza en cada corrida.
    conn = sqlite3.connect(":memory:" if a.demo or not a.db else a.db)
    if a.demo or not a.db:
        crear_base_demo(conn)
    repo = Repositorio(conn)

    # Función interna (closure) que captura repo y argumentos: el programador sólo recibe
    # un callable sin parámetros, sin saber nada de informes.
    def tarea() -> None:
        # Si es programado, agregamos la fecha al nombre para no pisar informes previos.
        salida = a.salida if not a.cada_dia else a.salida.with_name(f"{a.salida.stem}_{dt.date.today()}.pdf")
        generar_informe(repo, salida, a.desde, a.hasta)
        print(f"Informe generado: {salida}")

    if a.cada_dia:  # pragma: no cover - bucle infinito
        # "07:30" → (7, 30). Un formato inválido produce ValueError y la CLI termina con traza.
        h, m = map(int, a.cada_dia.split(":"))
        ejecutar_programado(Programacion(h, m), tarea)
    else:
        tarea()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
