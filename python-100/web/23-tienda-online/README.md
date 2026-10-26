# 23 · Clon básico de e-commerce

## Qué demuestra
API de tienda online con **FastAPI + SQLite**: catálogo administrable, carrito
anónimo, checkout con **pasarela de pago simulada**, descuento de stock
transaccional e **idempotencia** del pago (no cobra dos veces ante un doble clic).

## Arquitectura
```
tienda/pagos.py -> PasarelaPago (interfaz), PasarelaSimulada, validación Luhn y vencimiento
tienda/app.py   -> crear_app(): productos (admin), carritos, checkout
tests/          -> tests unitarios de pagos y end-to-end de la API
```
- Importes en **centavos** (enteros).
- La tarjeta se usa para cobrar y se descarta; solo se guardan los últimos 4 dígitos.
- Endpoints de administración protegidos con `X-Admin-Token` (variable `TIENDA_ADMIN_TOKEN`).

### Tarjetas de prueba (pasarela simulada)
| Número | Resultado |
|---|---|
| 4242 4242 4242 4242 | Aprobada |
| 4000 0000 0000 0002 | Rechazada |
| 4000 0000 0000 9995 | Fondos insuficientes |

## Instalación
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Uso
```bash
export TIENDA_ADMIN_TOKEN=un-token-largo TIENDA_DB=tienda.db
uvicorn tienda.app:app --reload   # docs en /docs
```

## Tests
```bash
pytest
```

## Limitaciones
- **No procesa pagos reales.** Para producción, implementar `PasarelaPago` con el SDK del proveedor y usar su tokenización (los datos de tarjeta nunca deberían pasar por tu servidor — PCI DSS).
- Sin cuentas de cliente ni envío.
