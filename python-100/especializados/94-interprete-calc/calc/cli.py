"""REPL y ejecución de archivos.

* ``python -m calc``: REPL. Comandos ``:vars``, ``:funcs`` y ``:salir``.
* ``python -m calc programa.calc``: ejecuta un archivo y muestra el último valor.
* ``python -m calc -e "2^10"``: evalúa una expresión.
"""
from __future__ import annotations

import sys
from pathlib import Path

from .errores import ErrorCalc
from .evaluador import Interprete, formatear


def repl(entrada=input, salida=print) -> None:
    """Bucle interactivo. Comandos: :vars, :funcs, :salir/:q. Un error se muestra y el REPL
    sigue (las variables definidas se conservan). ``entrada`` y ``salida`` se inyectan
    para poder probarlo.
    """
    it = Interprete()
    salida("Calc — escribí expresiones; ':salir' para terminar.")
    while True:
        try:
            linea = entrada("calc> ")
        except EOFError:
            break
        linea = linea.strip()
        if linea in (":salir", ":q"):
            break
        if linea == ":vars":
            salida(", ".join(f"{k}={formatear(v)}" for k, v in sorted(it.globales.items())) or "(ninguna)")
            continue
        if linea == ":funcs":
            salida(", ".join(f"{d.nombre}({', '.join(d.params)})" for d in it.funciones.values()) or "(ninguna)")
            continue
        if not linea:
            continue
        try:
            v = it.ejecutar(linea)
        except ErrorCalc as e:
            salida(str(e))
        else:
            if v is not None:
                salida(formatear(v))


def main(argv: list[str] | None = None) -> int:
    """Sin argumentos abre el REPL; con '-e EXPR' evalúa la expresión; con una ruta ejecuta el
    archivo. Errores de lenguaje o de lectura → stderr y código 1.
    """
    argv = sys.argv[1:] if argv is None else argv
    try:
        if not argv:
            repl()
            return 0
        fuente = argv[1] if argv[0] == "-e" and len(argv) > 1 else Path(argv[0]).read_text(encoding="utf-8")
        print(formatear(Interprete().ejecutar(fuente)))
        return 0
    except ErrorCalc as e:
        print(e, file=sys.stderr)
        return 1
    except OSError as e:
        print(f"no se pudo leer: {e}", file=sys.stderr)
        return 1
