"""Extracción de texto (pypdf) y de campos (expresiones regulares).

Las facturas reales varían mucho de formato; por eso cada campo tiene varios
patrones alternativos (etiquetas en español e inglés) y el resultado se valida
después. Lo que no se pueda extraer queda en ``None`` y va a revisión manual.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pypdf import PdfReader


@dataclass
class DatosFactura:
    numero: str | None = None
    fecha: dt.date | None = None
    proveedor: str | None = None
    id_fiscal: str | None = None  # CUIT / NIF / RFC
    subtotal: Decimal | None = None
    iva: Decimal | None = None
    total: Decimal | None = None
    # Moneda por defecto; se cambia si el texto menciona USD o EUR.
    moneda: str = "ARS"


def texto_pdf(ruta: Path) -> str:
    """Concatena el texto de todas las páginas. (PDFs escaneados necesitarían OCR.)"""
    # extract_text puede devolver None en páginas sin texto: se reemplaza por "".
    return "\n".join(p.extract_text() or "" for p in PdfReader(str(ruta)).pages)


def parsear_importe(texto: str) -> Decimal | None:
    """Convierte ``"1.234,56"``, ``"1,234.56"``, ``"1234.5"`` o ``"$ 99"`` a ``Decimal``.

    Heurística: el ÚLTIMO separador (``.`` o ``,``) seguido de 1-2 dígitos
    finales es el decimal; los demás son separadores de miles.
    """
    # Se descarta todo menos dígitos, separadores y signo ("$ 1.234,56" → "1.234,56").
    t = re.sub(r"[^\d.,-]", "", texto)
    if not t:
        return None
    # Ejemplos: "1.234,56" → decimal "56"; "1,234.56" → "56"; "1234.5" → "5";
    # "1.234" (3 dígitos al final) → se interpreta como miles, sin decimales.
    m = re.search(r"[.,](\d{1,2})$", t)
    if m:
        entero, dec = t[: m.start()], m.group(1)
    else:
        entero, dec = t, "0"
    entero = re.sub(r"[.,]", "", entero)
    try:
        # Decimal (no float): los importes contables no toleran errores binarios como 0.1+0.2.
        # quantize fija 2 decimales ("1234.5" → 1234.50).
        return Decimal(f"{entero or '0'}.{dec}").quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


# Importe: símbolo de moneda opcional y un número que termina en dígito (no captura el punto final).
IMPORTE = r"(?:[$€]|USD|ARS|EUR)?\s*(-?[\d.,]+\d)"
PATRONES = {
    # Cada campo tiene una lista de patrones alternativos; gana el primero que coincide.
    "numero": [r"(?:Factura|Invoice|Comprobante)\s*(?:N[°º.o]*|#|No\.?)\s*:?\s*([A-Z]?-?[\w-]*\d)"],
    "fecha": [r"Fecha(?: de emisi[oó]n)?\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4})", r"Date\s*:?\s*(\d{4}-\d{2}-\d{2})",
              r"Fecha\s*:?\s*(\d{4}-\d{2}-\d{2})"],
    "proveedor": [r"(?:Proveedor|Raz[oó]n social|Emisor|Vendor)\s*:\s*(.+)"],
    "id_fiscal": [r"(?:CUIT|NIF|CIF|RFC|Tax ID)\s*:?\s*([\w.-]{8,15})"],
    "subtotal": [rf"(?:Subtotal|Neto gravado|Base imponible)\s*:?\s*{IMPORTE}"],
    "iva": [rf"(?:IVA|VAT|Impuesto)[^\n:]*:\s*{IMPORTE}"],
    # El lookbehind (?<!Sub) evita que "Subtotal" se tome como total.
    "total": [rf"(?<!Sub)(?:TOTAL|Total a pagar|Importe total|Total)\s*:?\s*{IMPORTE}"],
}


def _buscar(campo: str, texto: str) -> str | None:
    for p in PATRONES[campo]:
        # "total" se busca sensible a mayúsculas para que el lookbehind "Sub" sea confiable; el resto ignora mayúsculas.
        m = re.search(p, texto, re.IGNORECASE if campo != "total" else 0)
        if m:
            return m.group(1).strip()
    return None


def _fecha(s: str) -> dt.date | None:
    # Se prioriza día/mes (convención local); ISO para facturas en inglés. 01/05 = 1 de mayo.
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def extraer_datos(texto: str) -> DatosFactura:
    d = DatosFactura()
    d.numero = _buscar("numero", texto)
    f = _buscar("fecha", texto)
    d.fecha = _fecha(f) if f else None
    d.proveedor = _buscar("proveedor", texto)
    d.id_fiscal = _buscar("id_fiscal", texto)
    # Los tres importes comparten el mismo tratamiento: buscar y parsear (None si falta).
    for campo in ("subtotal", "iva", "total"):
        v = _buscar(campo, texto)
        setattr(d, campo, parsear_importe(v) if v else None)
    # Detección de moneda por marcas en el texto; "U$S" es la forma usual en Argentina.
    if re.search(r"\bUSD\b|U\$S|US\$", texto):
        d.moneda = "USD"
    elif re.search(r"€|\bEUR\b", texto):
        d.moneda = "EUR"
    return d
