"""CLI: pdftablas informe.pdf salida.xlsx [--paginas 1-3] [--estrategia texto] [--decimal .] [--unir]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .excel import exportar_excel
from .extraer import extraer_tablas
from .limpieza import limpiar, unir_continuaciones


def ejecutar(argv: Sequence[str] | None = None) -> int:
    """Exit codes: 0 ok, 1 PDF inexistente/ilegible o páginas inválidas, 2 ninguna tabla encontrada."""
    p = argparse.ArgumentParser(prog="pdftablas")
    p.add_argument("pdf", type=Path); p.add_argument("salida", type=Path)
    p.add_argument("--paginas", help="ej. 1,3-5")
    p.add_argument("--estrategia", choices=["lineas", "texto"], default="lineas")
    # Por defecto coma decimal (informes en español).
    p.add_argument("--decimal", choices=[",", "."], default=",")
    p.add_argument("--sin-numeros", action="store_true", help="no convertir números")
    p.add_argument("--unir", action="store_true", help="unir tablas partidas entre páginas")
    a = p.parse_args(argv)
    try:
        crudas = extraer_tablas(a.pdf, a.paginas, a.estrategia)
    except (OSError, ValueError) as exc:
        # Archivo inexistente / sin permisos, o rango de páginas inválido.
        print(f"Error: {exc}", file=sys.stderr); return 1
    except Exception as exc:  # pdfminer lanza varios tipos ante PDFs corruptos
        print(f"PDF ilegible: {exc}", file=sys.stderr); return 1
    # Tablas con sólo encabezado (o vacías tras limpiar) no aportan datos: se descartan.
    tablas = [t for t in (limpiar(t, a.decimal, not a.sin_numeros) for t in crudas) if len(t.filas) > 1]
    if a.unir:
        tablas = unir_continuaciones(tablas)
    if not tablas:
        # Pista útil: sin bordes conviene "texto"; un escaneo no tiene texto extraíble.
        print("No se encontraron tablas (probá --estrategia texto; si es un escaneo hace falta OCR)", file=sys.stderr)
        return 2
    exportar_excel(tablas, a.salida)
    # Resumen por tabla: filas de datos (sin contar el encabezado) × columnas.
    for t in tablas:
        print(f"Página {t.pagina}, tabla {t.indice + 1}: {len(t.filas) - 1} fila(s) × {len(t.encabezado)} col.")
    print(f"Guardado en {a.salida}")
    return 0


def main() -> None:
    sys.exit(ejecutar())
