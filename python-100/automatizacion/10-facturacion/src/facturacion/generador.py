"""Genera facturas PDF de ejemplo con fpdf2 (para tests y demo).

Usamos texto real (no imágenes) para que pypdf pueda extraerlo, como en las
facturas electrónicas.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from fpdf import FPDF


def _fmt(v: Decimal, estilo: str) -> str:
    """Formatea un importe al estilo ``ar`` (1.234,56) o ``us`` (1,234.56)."""
    s = f"{v:,.2f}"
    # Intercambio de separadores con un marcador temporal "X" (si no, el segundo replace pisaría el primero).
    return s.replace(",", "X").replace(".", ",").replace("X", ".") if estilo == "ar" else s


def generar_factura_pdf(ruta: Path, *, proveedor: str, numero: str, fecha: str, items: list[tuple[str, int, Decimal]],
                        tasa_iva: Decimal = Decimal("0.21"), id_fiscal: str = "30-71234567-9",
                        estilo: str = "ar", simbolo: str = "$", total_forzado: Decimal | None = None) -> Path:
    # sum con valor inicial Decimal(0) para no mezclar int y Decimal; luego se redondea a centavos.
    subtotal = sum((Decimal(c) * p for _, c, p in items), Decimal(0)).quantize(Decimal("0.01"))
    iva = (subtotal * tasa_iva).quantize(Decimal("0.01"))
    # total_forzado permite fabricar facturas inconsistentes para probar la validación.
    total = total_forzado if total_forzado is not None else subtotal + iva
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    # El texto imita las etiquetas de una factura real para que los regex del extractor las encuentren.
    pdf.cell(0, 10, f"FACTURA N° {numero}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=11)
    for linea in (f"Proveedor: {proveedor}", f"CUIT: {id_fiscal}", f"Fecha de emisión: {fecha}", ""):
        pdf.cell(0, 7, linea, new_x="LMARGIN", new_y="NEXT")
    for desc, cant, precio in items:
        pdf.cell(100, 7, desc)
        pdf.cell(20, 7, str(cant))
        pdf.cell(0, 7, f"{simbolo} {_fmt(precio, estilo)}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.cell(0, 7, f"Subtotal: {simbolo} {_fmt(subtotal, estilo)}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, f"IVA {int(tasa_iva * 100)}%: {simbolo} {_fmt(iva, estilo)}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, f"TOTAL: {simbolo} {_fmt(total, estilo)}", new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(ruta))
    return ruta
