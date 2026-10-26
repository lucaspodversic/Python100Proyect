# 77 · Pasarela de pagos simulada

API con **FastAPI + SQLAlchemy + SQLite** que reproduce los mecanismos clave de una pasarela de pagos real: **claves de idempotencia**, **reembolsos parciales**, **webhooks firmados con HMAC** y entrega con reintentos (patrón *outbox*).

> ⚠️ **Es una simulación educativa.** No se conecta a Stripe, Mercado Pago ni a ningún banco y no procesa dinero real. No uses números de tarjeta reales; la app nunca guarda el número completo, solo la marca y los 4 últimos dígitos.

## Qué demuestra

- **Idempotencia**: las operaciones que mueven dinero (`POST /pagos` y `POST /pagos/{id}/reembolsos`) requieren la cabecera `Idempotency-Key`.
  - Si se repite la misma petición, se devuelve la respuesta guardada con `Idempotent-Replayed: true`.
  - Si se reutiliza la clave con otra petición, se responde 422.
  - La clave es única por comercio (`UNIQUE(comercio_id, clave)`), y las transacciones `BEGIN IMMEDIATE` serializan los reintentos simultáneos.
- **Reembolsos parciales**: la suma de reembolsos nunca supera el monto pagado. Lo garantizan la validación en el servicio y un `CHECK` en la base de datos. Hay un test con 8 hilos concurrentes.
- **Tarjetas de prueba** con validación de Luhn, detección de marca y control de vencimiento:

  | Número | Resultado |
  |---|---|
  | 4242 4242 4242 4242 | aprobada |
  | 5555 5555 5555 4444 | aprobada (Mastercard) |
  | 4000 0000 0000 0002 | `tarjeta_rechazada` (402) |
  | 4000 0000 0000 9995 | `fondos_insuficientes` (402) |

- **Webhooks**: cada evento (`pago.aprobado`, `pago.rechazado`, `reembolso.creado`) se guarda en la misma transacción que el cambio que lo origina (patrón *outbox*) y se entrega firmado:

  ```
  Firma-Pasarela: t=1775037600,v1=<HMAC-SHA256(secreto, "t.cuerpo")>
  ```

  `app/webhooks.py` incluye `verificar()` para el receptor. Compara en tiempo constante y aplica una tolerancia de 5 minutos contra repeticiones. Los fallos se reintentan hasta 5 veces.
- IDs públicos opacos (`pay_…`, `re_…`, `evt_…`), sin IDs secuenciales a la vista.

## Arquitectura

```
app/
├── tarjetas.py  # Luhn, marca, procesador simulado (sin dependencias)
├── webhooks.py  # firmar / verificar HMAC (sin dependencias, reutilizable)
├── servicio.py  # idempotencia, cobro, reembolso, outbox y despacho
└── main.py      # rutas; transporte HTTP y reloj inyectables
```

## Instalación y uso

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
# 1) POST /auth/registro, 2) POST /auth/login, 3) POST /webhook {"url": "https://mi-tienda/hook"}
curl -X POST localhost:8000/pagos -H "Authorization: Bearer $TOKEN" -H "Idempotency-Key: pedido-123" \
     -H "Content-Type: application/json" \
     -d '{"monto_centavos": 15000, "moneda": "ARS", "tarjeta": {"numero": "4242424242424242", "mes": 12, "anio": 2030}}'
```

## Tests

```bash
pytest
```

Los tests usan un transporte falso en memoria, así que no tocan la red. También simulan un receptor caído para probar los reintentos.

## Limitaciones

- Sin cumplimiento PCI-DSS. En un sistema real el número de tarjeta nunca debería llegar a tu servidor (se usa tokenización del lado del cliente).
- No hay flujo de autorizar y luego capturar, ni contracargos, 3-D Secure o conversión de moneda.
- El despacho de webhooks se dispara manualmente (`POST /eventos/despachar`). En producción lo haría un worker con *backoff* exponencial.
- El secreto del webhook se guarda en claro porque hace falta para firmar. En producción iría en un gestor de secretos o cifrado.
- Las claves de idempotencia no caducan.
