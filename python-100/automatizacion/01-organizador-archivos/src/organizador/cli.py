"""Interfaz de línea de comandos del organizador.

Ejemplos::

    organizador ~/Descargas --modo tipo_fecha --dry-run
    organizador ~/Fotos --modo fecha --plantilla "{fecha}_{indice:04d}"
    organizador ~/Descargas --deshacer
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .organizador import deshacer, ejecutar, planificar


def construir_parser() -> argparse.ArgumentParser:
    """Define los argumentos aceptados por la CLI."""
    # Reutilizamos el docstring del módulo como ayuda de ``--help`` (incluye los ejemplos).
    p = argparse.ArgumentParser(prog="organizador", description=__doc__)
    p.add_argument("origen", type=Path, help="carpeta a organizar")
    # Si no se indica destino, se organiza "en el lugar" (subcarpetas dentro del origen).
    p.add_argument("--destino", type=Path, default=None, help="carpeta raíz destino")
    p.add_argument(
        "--modo",
        choices=["tipo", "fecha", "tipo_fecha", "tamano"],
        default="tipo",
        help="criterio de clasificación",
    )
    p.add_argument("--plantilla", default=None, help="plantilla de renombrado")
    p.add_argument("-r", "--recursivo", action="store_true", help="incluye subcarpetas")
    # --dry-run es la forma segura de probar: imprime el plan y no toca ningún archivo.
    p.add_argument("--dry-run", action="store_true", help="sólo muestra el plan")
    p.add_argument("--deshacer", action="store_true", help="revierte la última ejecución")
    return p


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada; devuelve el código de salida del proceso."""
    # ``argv`` inyectable: los tests llaman ``main([...])`` sin tocar ``sys.argv``.
    args = construir_parser().parse_args(argv)
    # ``resolve()`` vuelve absoluta la ruta, así el registro guarda rutas válidas desde cualquier cwd.
    raiz = (args.destino or args.origen).resolve()
    # La CLI usa un nombre de registro visible para que el usuario lo encuentre.
    registro = raiz / "organizador_registro.json"
    # Modo deshacer: código de salida 1 si no hay nada que revertir (útil en scripts).
    if args.deshacer:
        if not registro.exists():
            print("No hay registro para deshacer.")
            return 1
        print(f"Restaurados {deshacer(registro)} archivos.")
        return 0
    # Primero siempre se planifica; ejecutar es una fase aparte (patrón plan/aplicar).
    plan = planificar(args.origen, args.destino, args.modo, args.plantilla, args.recursivo)
    for mov in plan:
        print(f"{mov.origen} -> {mov.destino}")
    if args.dry_run:
        print(f"[dry-run] {len(plan)} movimientos planificados, nada fue modificado.")
        return 0
    # Se guarda el registro para poder ejecutar luego ``--deshacer``.
    n = ejecutar(plan, registro)
    print(f"Movidos {n} archivos. Registro en {registro}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
