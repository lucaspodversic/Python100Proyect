# 69 · Extractor de tablas de PDF a Excel

Extrae tablas de PDFs con **pdfplumber**, las limpia (espacios, títulos, columnas vacías, números en
formato latino o anglosajón, porcentajes) y las guarda en **Excel** con openpyxl.

## Qué demuestra
- Dos estrategias: `lineas` (tablas con grilla) y `texto` (columnas alineadas sin bordes).
- Limpieza robusta y conversión de `1.250,50` / `1,250.50` / `15%` a números reales de Excel.
- Unión de tablas partidas entre páginas (encabezado repetido o filas sólo numéricas).
- Excel prolijo: una hoja por tabla, encabezado destacado, panel congelado, anchos ajustados, formato numérico.
- Tests con PDFs **generados en el momento** (`tests/pdf_fixture.py`, escritor PDF mínimo): sin binarios en el repo.

## Arquitectura
```
pdftablas/
  extraer.py   # Tabla, extraer_tablas, parsear_paginas
  limpieza.py  # convertir_numero, limpiar, unir_continuaciones
  excel.py     # exportar_excel
  cli.py
```

## Instalación y uso
```bash
pip install -e ".[dev]"
python -m pdftablas informe.pdf tablas.xlsx                       # tablas con bordes
python -m pdftablas extracto.pdf salida.xlsx --estrategia texto --paginas 2-5 --unir
python -m pdftablas report.pdf out.xlsx --decimal .               # números 1,234.56
```
Exit codes: 0 ok, 1 error de archivo, 2 sin tablas.

## Tests
```bash
pytest
```

## Limitaciones
- PDFs escaneados (imágenes) no tienen texto: requieren OCR (p. ej. Tesseract) antes.
- La estrategia `texto` necesita al menos 3 filas alineadas por columna (parámetro `min_words_vertical` de pdfplumber).
- Celdas combinadas complejas o tablas sin alineación clara pueden necesitar ajustar `table_settings`.
- Los PDFs de test sólo tienen texto (sin líneas), por eso la estrategia `lineas` no se cubre con fixtures propios.
