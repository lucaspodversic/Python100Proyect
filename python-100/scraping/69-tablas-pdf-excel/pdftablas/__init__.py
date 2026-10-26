"""pdftablas: extrae tablas de PDFs (pdfplumber) y las guarda en Excel (openpyxl)."""
# API pública: extracción → limpieza → exportación.
from .extraer import Tabla, extraer_tablas
from .limpieza import convertir_numero, limpiar, unir_continuaciones
from .excel import exportar_excel

__all__ = ["Tabla", "extraer_tablas", "convertir_numero", "limpiar", "unir_continuaciones", "exportar_excel"]
