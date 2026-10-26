# 26 · API de gestión de inventario

## Qué demuestra
Backend de control de stock **multi-almacén** con reglas de negocio reales:
entradas, salidas, ajustes por conteo físico (con nota obligatoria),
transferencias **atómicas** entre almacenes, **kardex** con saldo acumulado,
**costo promedio ponderado**, valuación total y alertas de bajo stock con
sugerencia de compra.

## Arquitectura
```
inventario/servicio.py -> Inventario: lógica de negocio + SQLite con transacciones (BEGIN IMMEDIATE)
inventario/app.py      -> FastAPI: endpoints y traducción de ErrorInventario a HTTP
tests/                 -> tests del servicio y de la API
```
La lógica no depende de FastAPI: se puede reutilizar desde una CLI o un worker.
El stock nunca puede quedar negativo (validación + `CHECK` en la tabla).

## Instalación
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Uso
```bash
INVENTARIO_DB=inventario.db uvicorn inventario.app:app
# Endpoints: POST /productos, /almacenes, /movimientos/{entrada|salida|ajuste|transferencia}
#            GET /productos/{id}/stock, /productos/{id}/kardex, /alertas/bajo-stock, /reportes/valuacion
```

## Tests
```bash
pytest
```

## Limitaciones
- Sin autenticación ni roles (agregar antes de exponerla).
- Sin lotes/vencimientos ni números de serie.
