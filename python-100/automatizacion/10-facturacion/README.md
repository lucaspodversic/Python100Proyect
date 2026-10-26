# 10 · Automatización de facturación

Extrae datos de facturas PDF (número, fecha, proveedor, CUIT/NIF, subtotal, IVA, total, moneda), los **valida** y genera el **asiento contable** en partida doble.

## Qué demuestra
- Extracción de texto con `pypdf` y de campos con expresiones regulares tolerantes (español/inglés, formatos `1.234,56` y `1,234.56`).
- Montos con `Decimal`, nunca `float`.
- Validación de negocio: campos obligatorios, fecha futura, `subtotal + IVA = total`, duplicados (proveedor + número).
- Interfaz `SistemaContable` + implementación SQLite con asientos (Gastos / IVA crédito fiscal / Proveedores).
- Procesamiento por lotes resiliente: un PDF corrupto va a revisión y no frena el resto.
- Generador de facturas con `fpdf2` para tests y demo.

## Arquitectura
```
src/facturacion/
├── extractor.py     # texto_pdf(), parsear_importe(), extraer_datos() -> DatosFactura
├── validacion.py    # validar() -> lista de problemas
├── contabilidad.py  # SistemaContable (Protocol), SQLiteContabilidad (+ balance())
├── procesador.py    # Procesador.procesar_carpeta(), exportar_revision()
├── generador.py     # generar_factura_pdf() (fpdf2)
└── cli.py
```

## Instalación
```bash
pip install -e ".[dev]"
```

## Uso
```bash
facturacion demo ./bandeja
facturacion procesar ./bandeja --db contabilidad.db --mover --revision revision.csv
```

## Tests
```bash
pytest
```
Los PDFs se generan en `tmp_path` en cada test (no hay binarios en el repo) y la base es SQLite en memoria.

## Limitaciones
- PDFs escaneados (imagen) necesitan OCR (p. ej. `pytesseract`), que no está incluido.
- Las regex cubren formatos comunes; proveedores con diseños exóticos requieren patrones propios. Lo que no se extrae va a revisión, nunca se contabiliza a ciegas.
- Para integrar un ERP real (Xero, QuickBooks, Odoo…) hay que implementar `SistemaContable` con su API.
