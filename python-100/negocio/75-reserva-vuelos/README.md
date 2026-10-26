# 75 · Sistema de reserva de vuelos

Backend con **FastAPI + SQLAlchemy + SQLite** que simula la búsqueda de vuelos, el mapa de asientos y la reserva en dos pasos: **retención** temporal y **confirmación**. Usa precios dinámicos.

## Qué demuestra

- **Sin doble venta**: la tabla `asientos_ocupados` tiene clave primaria `(vuelo_id, asiento)`, así que la base de datos rechaza un segundo intento de ocupar el mismo asiento. Un test lanza 10 hilos sobre el mismo asiento y gana exactamente uno.
- **Retención con expiración** (15 minutos): si la reserva no se confirma a tiempo pasa a `expirada` y el asiento se libera solo. El reloj es inyectable, así que los tests "adelantan el tiempo" sin esperar.
- **Precio dinámico**: `base × (1 + 0,5 × ocupación)`. El precio queda fijo al momento de retener.
- **Localizador PNR** de 6 caracteres sin letras ambiguas, generado con `secrets`.
- Validaciones: formato de asiento (`12C`), asiento existente en la cabina, vuelos ya despegados, origen distinto del destino y códigos IATA.
- Privacidad: un cliente no puede confirmar ni cancelar reservas ajenas (recibe 404).

## Arquitectura

```
app/
├── modelos.py   # Vuelo, Reserva, AsientoOcupado (candado), Usuario, Token
├── servicio.py  # búsqueda, mapa, retener/confirmar/cancelar, precios, expiración
├── main.py      # rutas + crear_app(reloj=...)
└── auth.py, seguridad.py, db.py
```

| Ruta | Descripción |
|---|---|
| `POST /vuelos` (admin) | alta de vuelo |
| `GET /vuelos/buscar?origen=EZE&destino=MDZ&fecha=2026-03-10` | búsqueda |
| `GET /vuelos/{id}/asientos` | mapa `{asiento: libre}` |
| `POST /reservas` | retener asiento → PNR |
| `POST /reservas/{pnr}/confirmar` · `/cancelar` | confirmar o cancelar |
| `GET /reservas` | mis reservas |

## Instalación y uso

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export VUELOS_ADMIN_PASSWORD="clave-segura"
uvicorn app.main:app --reload
```

## Tests

```bash
pytest
```

## Limitaciones

- La confirmación simula el pago: no hay pasarela real.
- Las fechas se guardan en UTC sin zona horaria (es una convención documentada del proyecto).
- No hay escalas, clases tarifarias ni equipaje.
- La colisión de PNR, aunque astronómicamente improbable, no se reintenta.
