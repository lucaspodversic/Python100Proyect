"""Extracción con pdfplumber.

Dos estrategias:
- "lineas": usa los bordes dibujados de la tabla (ideal para tablas con grilla).
- "texto": infiere columnas por la alineación de las palabras (tablas sin bordes).
PDFs escaneados (imágenes) no tienen texto: requerirían OCR.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

# Nombre en español → table_settings de pdfplumber (vertical = columnas, horizontal = filas).
ESTRATEGIAS = {
    "lineas": {"vertical_strategy": "lines", "horizontal_strategy": "lines"},
    "texto": {"vertical_strategy": "text", "horizontal_strategy": "text"},
}


@dataclass
class Tabla:
    """Tabla extraída. Mutable a propósito: unir_continuaciones extiende las filas."""

    pagina: int              # 1-based, como lo ve una persona
    indice: int              # n.º de tabla dentro de la página
    filas: list[list]        # celdas: str (crudo) o str/float tras limpiar

    @property
    def encabezado(self) -> list:
        """Primera fila (o [] si la tabla quedó vacía tras limpiar)."""
        return self.filas[0] if self.filas else []


def parsear_paginas(texto: str | None, total: int) -> list[int]:
    """'1,3-5' → [1,3,4,5] (1-based). None → todas."""
    if not texto:
        return list(range(1, total + 1))
    res: list[int] = []
    for parte in texto.split(","):
        # partition: "3-5" → ("3", "-", "5"); "1" → ("1", "", "") → fin = inicio.
        a, _, b = parte.strip().partition("-")
        ini, fin = int(a), int(b or a)   # texto no numérico → ValueError de int()
        # Rechaza rangos invertidos (5-3), página 0 y páginas fuera del PDF.
        if not (1 <= ini <= fin <= total):
            raise ValueError(f"Rango de páginas inválido: {parte!r} (el PDF tiene {total})")
        res.extend(range(ini, fin + 1))
    # set: "1-3,2" no repite la página 2; sorted: siempre en orden del documento.
    return sorted(set(res))


def extraer_tablas(pdf: Path | bytes, paginas: str | None = None, estrategia: str = "lineas") -> list[Tabla]:
    """Tablas crudas (celdas str) de las páginas pedidas, en orden de página y de aparición."""
    if estrategia not in ESTRATEGIAS:
        raise ValueError(f"Estrategia desconocida: {estrategia}")
    # Acepta bytes (PDF en memoria, útil en tests y servicios web) o una ruta.
    fuente = io.BytesIO(pdf) if isinstance(pdf, bytes) else pdf
    tablas: list[Tabla] = []
    with pdfplumber.open(fuente) as doc:
        for n in parsear_paginas(paginas, len(doc.pages)):
            # doc.pages es 0-based; n es 1-based.
            for i, filas in enumerate(doc.pages[n - 1].extract_tables(ESTRATEGIAS[estrategia])):
                # pdfplumber devuelve None en celdas vacías/fusionadas: se normaliza a "".
                tablas.append(Tabla(n, i, [[c if c is not None else "" for c in f] for f in filas]))
    return tablas
