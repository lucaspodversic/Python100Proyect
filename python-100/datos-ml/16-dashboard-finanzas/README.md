# 16 · Dashboard de finanzas personales

Aplicación web con **Dash + Plotly** que visualiza ingresos y gastos a partir de un CSV del home banking: KPIs, gráficos mensuales, gastos por categoría, saldo acumulado y control de presupuesto.

## Qué demuestra
- Normalización robusta de CSVs reales: detecta el separador `;` o `,`, montos `1.234,56` o `1,234.56`, `monto` o `debito`/`credito`, y fechas en dos formatos.
- Categorización automática por palabras clave (Coto → Supermercado, Edenor → Servicios…).
- Separación limpia de capas:
  - `analisis` contiene cálculos puros;
  - `graficos` arma las figuras;
  - `app` maneja el layout y los callbacks.
- La lógica del callback es una función pura (`actualizar`), así que se testea sin servidor.
- Exportación a HTML estático (sin servidor) para compartir el reporte.
- El servidor escucha sólo en `127.0.0.1`, porque los datos financieros no se exponen a la red.

## Arquitectura
```
src/finanzas/
├── datos.py     # cargar_movimientos(), categorizar(), generar_demo()
├── analisis.py  # resumen_mensual(), gastos_por_categoria(), kpis(), control_presupuesto()
├── graficos.py  # fig_mensual(), fig_categorias(), fig_saldo()
├── app.py       # crear_app(), actualizar(), tabla_presupuesto()
└── cli.py
```

## Instalación
```bash
pip install -e ".[dev]"
```

## Uso
```bash
dashboard-finanzas --demo                       # abrir http://127.0.0.1:8050
dashboard-finanzas movimientos.csv
dashboard-finanzas movimientos.csv --exportar reporte.html
```
Columnas mínimas: `fecha, descripcion` (o `concepto`/`detalle`) y `monto` (o `importe`, o `debito`+`credito`). `categoria` es opcional.

## Tests
```bash
pytest
```
Cubren la carga en distintos formatos, los cálculos, las figuras, el callback y el layout. Además, se verificó a mano que el servidor responde (`GET /` y el callback `/_dash-update-component`).

## Limitaciones
- Las reglas de categorización están pensadas para comercios argentinos; se editan en `REGLAS_CATEGORIA`.
- No maneja múltiples monedas ni transferencias entre cuentas propias (se cuentan como ingreso/gasto).
- No hay autenticación: es para uso local.
