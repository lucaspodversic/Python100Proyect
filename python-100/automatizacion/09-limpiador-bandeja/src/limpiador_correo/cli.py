"""CLI: ``limpiador-bandeja reglas.json [--aplicar] [--max 500] [--proteger jefe@empresa.com]``.

Por defecto es dry-run: muestra qué haría sin modificar nada.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .gmail import GmailCliente, crear_servicio
from .motor import Motor, cargar_reglas


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - requiere OAuth real
    ap = argparse.ArgumentParser(prog="limpiador-bandeja", description=__doc__)
    ap.add_argument("reglas", type=Path)
    # Misma sintaxis de búsqueda que la caja de Gmail ("in:inbox older_than:1y", etc.).
    ap.add_argument("--consulta", default="in:inbox")
    # Tope de correos por corrida: limita cuota de API y el daño de una regla mal escrita.
    ap.add_argument("--max", type=int, default=500)
    # Seguridad por defecto: sin --aplicar sólo se muestra el plan (dry-run).
    ap.add_argument("--aplicar", action="store_true")
    # Repetible: --proteger jefe@x.com --proteger banco.com (coincidencia por subcadena).
    ap.add_argument("--proteger", action="append", default=[])
    ap.add_argument("--credenciales", default="credentials.json")
    a = ap.parse_args(argv)
    motor = Motor(GmailCliente(crear_servicio(a.credenciales)), cargar_reglas(a.reglas), a.proteger)
    # Se imprime el resumen tanto en dry-run como al aplicar, para dejar registro.
    print(motor.ejecutar(a.consulta, a.max, dry_run=not a.aplicar).resumen())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
