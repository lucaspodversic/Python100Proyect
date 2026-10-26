"""Interfaz de línea de comandos.

Por seguridad la contraseña se pide con getpass (no queda en el
historial de la shell). También se aceptan varias por stdin con --stdin.
"""
from __future__ import annotations

import argparse
import getpass
import sys
from typing import Sequence, TextIO

from .cliente_http import ClienteHIBP
from .nucleo import ClienteRango, comprobar


def ejecutar(argv: Sequence[str] | None = None, cliente: ClienteRango | None = None,
             entrada: TextIO | None = None, salida: TextIO | None = None) -> int:
    """Punto de entrada testeable. Devuelve código de salida:
    0 = ninguna comprometida, 1 = alguna comprometida, 2 = error."""
    # Se construye el parser en cada llamada para que los tests puedan invocar ejecutar() varias veces.
    parser = argparse.ArgumentParser(prog="pwncheck", description="Comprueba contraseñas en HIBP")
    parser.add_argument("--stdin", action="store_true", help="Leer una contraseña por línea desde stdin")
    args = parser.parse_args(argv)
    # Inyección de dependencias: si el test no pasa un cliente/entrada/salida, se usan los reales.
    cliente = cliente or ClienteHIBP()
    entrada = entrada or sys.stdin
    salida = salida or sys.stdout

    # Modo lote: una contraseña por línea; se descartan líneas en blanco.
    # rstrip("\n") (y no strip()) respeta espacios iniciales/finales, que son parte de la contraseña.
    if args.stdin:
        contrasenas = [l.rstrip("\n") for l in entrada if l.strip()]
    # Modo interactivo: getpass no muestra lo tecleado ni lo deja en el historial de la shell.
    else:
        contrasenas = [getpass.getpass("Contraseña: ")]

    # Se recuerda si al menos una apareció, para decidir el código de salida al final.
    alguna = False
    # Se numeran desde 1 para que la salida sea legible por humanos.
    for i, pwd in enumerate(contrasenas, start=1):
        try:
            r = comprobar(pwd, cliente)
        # Ante cualquier error se aborta con 2: un resultado parcial podría dar falsa sensación de seguridad.
        except Exception as exc:  # Error de red o validación
            print(f"[{i}] error: {exc}", file=salida)
            return 2
        # Nunca imprimimos la contraseña, sólo su índice
        if r.comprometida:
            alguna = True
            print(f"[{i}] COMPROMETIDA: vista {r.apariciones} veces. ¡Cambiala!", file=salida)
        else:
            print(f"[{i}] no encontrada en filtraciones conocidas", file=salida)
    # Códigos pensados para scripts/CI: 1 permite bloquear un pipeline si hay contraseñas filtradas.
    return 1 if alguna else 0


# Entrada del script de consola: convierte el código devuelto en el exit status del proceso.
def main() -> None:
    sys.exit(ejecutar())


# Permite ejecutar también `python pwncheck/cli.py` directamente.
if __name__ == "__main__":
    main()
