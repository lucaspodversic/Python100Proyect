# 08 · Monitor de precios de vuelos

Rastrea el precio de un vuelo específico, guarda el **historial** y envía una **alerta** cuando baja de un umbral (o cae un % respecto del mínimo visto).

## Qué demuestra
- Integración con una **API oficial** (Amadeus Self-Service, *Flight Offers Search v2*) con OAuth2 `client_credentials` y caché de token.
- Transporte HTTP inyectable: los tests no tocan la red.
- Reglas de alerta puras con anti-spam (sólo re-alerta si el precio mejora).
- Historial en SQLite (serie de precios, mínimo previo, alertas emitidas).
- Notificadores intercambiables: consola o webhook (Slack/Discord/Teams).

## Arquitectura
```
src/monitor_vuelos/
├── modelos.py        # Seguimiento, Cotizacion
├── proveedores.py    # ProveedorVuelos (Protocol), AmadeusProveedor, FakeProveedor
├── historial.py      # Historial (SQLite)
├── monitor.py        # evaluar_alerta(), Monitor.revisar()/vigilar()
├── notificadores.py  # Consola, Webhook, Fake
└── cli.py
```

## Instalación
```bash
pip install -e ".[dev]"
```

## Uso
1. Creá una app gratuita en <https://developers.amadeus.com> (entorno *test*) y exportá las credenciales:
```bash
export AMADEUS_CLIENT_ID=... AMADEUS_CLIENT_SECRET=...
export MONITOR_WEBHOOK=https://hooks.slack.com/services/...   # opcional
monitor-vuelos EZE MAD 2025-03-10 --umbral 900 --caida 10 --cada 3600 --veces 24
```
2. Sin credenciales: `monitor-vuelos EZE MAD 2025-03-10 --umbral 900 --demo --veces 3`.

## Tests
```bash
pytest
```
Proveedor y transporte falsos (respuestas con la forma real de Amadeus), SQLite en memoria y reloj controlado.

## Limitaciones
- El entorno *test* de Amadeus devuelve datos cacheados/no reales; para precios reales se necesita el entorno de producción.
- No se consultan sitios de aerolíneas por scraping (sus términos lo prohíben); sólo APIs oficiales.
- El adaptador Amadeus se validó con respuestas simuladas, no contra la API real (sin credenciales en este entorno).
