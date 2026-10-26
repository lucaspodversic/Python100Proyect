"""Composición del PDF con fpdf2: portada, KPIs, gráficos y tablas."""

from __future__ import annotations

import datetime as dt
import tempfile
from pathlib import Path

from fpdf import FPDF

from .datos import Repositorio
from .graficos import grafico_barras, grafico_linea


def _moneda(v: float) -> str:
    """Formato ``$ 1.234.567,89`` (estilo es-AR) sin depender del locale del SO."""
    # Truco sin locale: Python formatea "1,234,567.89" (en-US) y luego cambiamos las comas
    # de miles por puntos y el punto decimal por coma → "1.234.567,89".
    entero, dec = f"{v:,.2f}".split(".")
    return f"$ {entero.replace(',', '.')},{dec}"


class InformePDF(FPDF):
    """PDF con encabezado y pie de página en todas las hojas."""

    def __init__(self, titulo: str) -> None:
        super().__init__(format="A4")
        self.titulo = titulo
        # Salto de página automático a 15 mm del borde inferior (deja lugar al pie).
        self.set_auto_page_break(auto=True, margin=15)

    # fpdf2 llama a header() y footer() automáticamente en cada página nueva.
    def header(self) -> None:
        self.set_font("Helvetica", "B", 12)
        self.cell(0, 8, self.titulo, align="L")
        self.ln(10)

    def footer(self) -> None:
        # Posición negativa = medida desde el borde inferior.
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        # "{nb}" (llaves dobles para escaparlas en el f-string) es el alias que fpdf reemplaza por el
        # total de páginas al cerrar el documento (ver alias_nb_pages).
        self.cell(0, 8, f"Página {self.page_no()}/{{nb}}", align="C")

    def tabla(self, cabecera: list[str], filas: list[list[str]], anchos: list[int]) -> None:
        """Tabla simple con cabecera sombreada y filas alternadas."""
        self.set_font("Helvetica", "B", 10)
        # Mismo azul (#305496) que los gráficos, para una identidad visual coherente.
        self.set_fill_color(48, 84, 150)
        self.set_text_color(255)
        for c, w in zip(cabecera, anchos):
            self.cell(w, 7, c, border=1, fill=True, align="C")
        self.ln()
        self.set_font("Helvetica", "", 10)
        self.set_text_color(0)
        for i, fila in enumerate(filas):
            # Filas alternadas ("cebra") para facilitar la lectura de tablas largas.
            self.set_fill_color(235, 241, 222) if i % 2 else self.set_fill_color(255, 255, 255)
            for j, (v, w) in enumerate(zip(fila, anchos)):
                # Primera columna (texto) alineada a la izquierda; números a la derecha.
                self.cell(w, 7, v, border=1, fill=True, align="L" if j == 0 else "R")
            self.ln()
        self.ln(4)


def generar_informe(repo: Repositorio, destino: Path, desde: str, hasta: str, titulo: str = "Informe de ventas") -> Path:
    """Genera el PDF completo y devuelve su ruta.

    Los PNG intermedios se crean en un directorio temporal que se borra solo.
    """
    k = repo.kpis(desde, hasta)
    pdf = InformePDF(titulo)
    # Habilita el reemplazo de "{nb}" por el total de páginas.
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    # new_x/new_y (API moderna de fpdf2) reemplazan al parámetro ``ln`` obsoleto: siguiente línea.
    pdf.cell(0, 12, titulo, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, f"Período: {desde} a {hasta}  -  Generado: {dt.datetime.now():%Y-%m-%d %H:%M}",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    # Las unidades se formatean con punto de miles (convención es-AR).
    pdf.tabla(["Indicador", "Valor"], [
        ["Facturación", _moneda(k["facturacion"])],
        ["Unidades vendidas", f"{int(k['unidades']):,}".replace(",", ".")],
        ["Operaciones", str(int(k["operaciones"]))],
        ["Ticket promedio", _moneda(k["ticket_promedio"])],
    ], [90, 60])
    # Los PNG sólo se necesitan mientras se insertan: el directorio temporal se borra al salir.
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        mensual = repo.ventas_por_mes(desde, hasta)
        # Caso borde: sin datos en el período no se dibujan gráficos (matplotlib fallaría o quedaría vacío).
        if mensual:
            pdf.image(str(grafico_linea(mensual, "Facturación mensual", t / "mes.png")), w=180)
        regiones = repo.por_region(desde, hasta)
        if regiones:
            pdf.image(str(grafico_barras(regiones, "Facturación por región", t / "reg.png")), w=180)
    # Página 2: ranking de productos. Por eso un informe normal tiene exactamente 2 páginas.
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Top productos", new_x="LMARGIN", new_y="NEXT")
    pdf.tabla(["Producto", "Unidades", "Facturación"],
              [[p, str(u), _moneda(t)] for p, u, t in repo.top_productos(desde, hasta)], [70, 40, 60])
    pdf.output(str(destino))
    return destino
