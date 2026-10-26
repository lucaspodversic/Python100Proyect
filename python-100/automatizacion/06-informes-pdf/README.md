# 06 · Generador de informes en PDF

Toma datos de una **base de datos**, calcula indicadores y genera un **PDF con gráficos y tablas**; puede correr de forma **programada** (diaria/semanal).

## Qué demuestra
- Consultas SQL de negocio (KPIs, agregados por mes/región, ranking) con DB-API (`sqlite3`).
- Gráficos con matplotlib en modo *headless* (backend Agg) aptos para servidores/cron.
- Composición de PDF con `fpdf2`: encabezado/pie con "Página X/Y", tablas con filas alternadas e imágenes.
- Programador testeable (cálculo de próxima ejecución con reloj inyectable).

## Arquitectura
```
src/informes_pdf/
├── datos.py        # Repositorio (consultas), crear_base_demo (datos sintéticos)
├── graficos.py     # grafico_linea, grafico_barras -> PNG
├── informe.py      # InformePDF (fpdf2) y generar_informe()
├── programador.py  # Programacion, proxima_ejecucion, ejecutar_programado
└── cli.py
```

## Instalación
```bash
pip install -e ".[dev]"
```

## Uso
```bash
informes-pdf --demo -o informe.pdf                          # datos sintéticos
informes-pdf --db ventas.db --desde 2024-01-01 --hasta 2024-03-31 -o q1.pdf
informes-pdf --db ventas.db --cada-dia 07:30 -o diario.pdf   # proceso residente
```
Alternativa con cron: `30 7 * * * informes-pdf --db /datos/ventas.db -o /informes/diario.pdf`.

La tabla esperada es `ventas(fecha TEXT ISO, producto, region, unidades, precio_unitario)`.

## Tests
```bash
pytest
```
Base SQLite en memoria; el PDF generado se lee con `pypdf` para verificar textos, páginas e imágenes.

## Limitaciones
- Las fuentes núcleo de PDF (Helvetica) cubren Latin-1 (acentos y ñ); para otros alfabetos hay que registrar una fuente TTF.
- Las consultas usan funciones de fecha de SQLite (`substr`); en otro motor hay que adaptarlas.
