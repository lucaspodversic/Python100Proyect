# 71 · Sistema de reservas de hotel

Backend REST con **FastAPI + SQLAlchemy 2 + SQLite** que gestiona habitaciones, disponibilidad y reservas de clientes.

## Qué demuestra

- Modelado de un dominio real (usuarios, habitaciones, reservas) con SQLAlchemy 2 tipado.
- **Reservas sin solapamiento** usando intervalos semiabiertos `[entrada, salida)`: un huésped puede entrar el mismo día en que sale el anterior.
- **Control de concurrencia**: cada transacción se abre con `BEGIN IMMEDIATE`, así "comprobar + insertar" es atómico. Un test lanza 12 hilos que reservan la misma habitación a la vez y verifica que gana uno solo.
- **Roles** (`admin` / `cliente`): solo el admin da de alta habitaciones y ve todas las reservas; un cliente no puede ver ni cancelar reservas ajenas (responde 404 para no revelar que existen).
- Validaciones: fechas coherentes, nada en el pasado, máximo 30 noches, capacidad de la habitación.
- Seguridad básica: contraseñas con PBKDF2 y sal, tokens aleatorios guardados como SHA-256 y comparación en tiempo constante.
- Importes en centavos enteros (sin errores de redondeo).

## Arquitectura

```
app/
├── db.py         # motor SQLite + BEGIN IMMEDIATE (concurrencia)
├── modelos.py    # tablas ORM
├── esquemas.py   # validación Pydantic
├── seguridad.py  # contraseñas y tokens
├── servicio.py   # reglas de negocio (testeables sin HTTP)
└── main.py       # fábrica crear_app() + rutas
tests/            # API (TestClient) + concurrencia con hilos
```

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| POST | `/auth/registro` | público | alta de cliente |
| POST | `/auth/login` | público | devuelve un token Bearer |
| GET | `/habitaciones` | público | catálogo |
| POST | `/habitaciones` | admin | alta de habitación |
| GET | `/disponibilidad?entrada=&salida=&huespedes=` | público | habitaciones libres |
| POST | `/reservas` | cliente | crear reserva |
| GET | `/reservas` | cliente/admin | las propias (admin: todas) |
| POST | `/reservas/{id}/cancelar` | dueño/admin | cancelar |

## Instalación

```bash
python -m venv .venv && source .venv/bin/activate   # en Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Uso

```bash
export HOTEL_ADMIN_PASSWORD="una-clave-segura"   # crea el admin inicial admin@hotel.local
uvicorn app.main:app --reload
# Documentación interactiva: http://127.0.0.1:8000/docs
```

## Tests

```bash
pytest
```

Los tests usan una base SQLite temporal y una fecha "hoy" fija, sin red.

## Limitaciones

- SQLite serializa todas las escrituras: sirve para un hotel pequeño. Con más carga conviene PostgreSQL con una restricción `EXCLUDE USING gist` sobre el rango de fechas.
- Los tokens no expiran y no hay renovación ni revocación desde la API.
- No incluye pagos ni envío de emails de confirmación.
