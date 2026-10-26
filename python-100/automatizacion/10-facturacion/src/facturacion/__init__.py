"""Automatización de facturación: PDF -> datos -> validación -> asiento contable."""

# Flujo: PDF → texto (pypdf) → campos (regex) → validación → asiento contable (SQLite o sistema real).
from .extractor import DatosFactura, extraer_datos, parsear_importe, texto_pdf
from .validacion import validar
from .contabilidad import SistemaContable, SQLiteContabilidad
from .procesador import Procesador, Resultado
from .generador import generar_factura_pdf

__all__ = ["DatosFactura", "extraer_datos", "parsear_importe", "texto_pdf", "validar", "SistemaContable",
           "SQLiteContabilidad", "Procesador", "Resultado", "generar_factura_pdf"]
