# 73 · Sistema de gestión de empleados (RRHH)

Backend REST con **FastAPI + SQLAlchemy + SQLite** para gestionar legajos, ausencias (vacaciones, enfermedad, sin goce) y liquidación mensual de nóminas.

## Qué demuestra

- **Nómina con aritmética exacta**: `Decimal` con redondeo *half-up* a centavos. El descuento por ausencia sin goce se calcula como bruto/30 × días, y los aportes (11 % + 3 % + 3 %, valores de ejemplo configurables) se aplican sobre el resultado.
- **Ausencias sin solapamiento** (intervalos cerrados) y **saldo de vacaciones** anual por empleado.
- **Flujo de aprobación** solicitada → aprobada/rechazada. Nadie puede aprobar su propia ausencia.
- **Idempotencia**: la restricción `UNIQUE(empleado, período)` impide liquidar dos veces el mismo mes (devuelve 409).
- **Roles y privacidad**: un `empleado` solo ve su legajo y sus nóminas (`/yo/...`). `rrhh` gestiona y `admin` además asigna roles.
- Baja lógica: el historial se conserva.

## Arquitectura

```
app/
├── nomina.py     # cálculo puro (sin BD), 100 % testeable
├── servicio.py   # ausencias, saldo, liquidación del período
├── modelos.py    # Empleado, Ausencia, Nomina, Usuario, Token
├── auth.py, seguridad.py, db.py
└── main.py       # rutas y crear_app()
```

## Instalación y uso

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export RRHH_ADMIN_PASSWORD="clave-segura"     # admin inicial: admin@rrhh.local
uvicorn app.main:app --reload                 # docs en /docs
```

Flujo típico: el empleado se registra → RRHH crea su legajo con `usuario_id` → el empleado pide ausencias en `/yo/ausencias` → RRHH aprueba → `POST /nominas/2026-02` liquida el mes.

## Tests

```bash
pytest
```

## Limitaciones

- Los porcentajes de aportes son un ejemplo didáctico: no reemplazan el asesoramiento legal ni contable. Tampoco se calculan horas extra, aguinaldo ni impuesto a las ganancias.
- El saldo de vacaciones no tiene en cuenta la antigüedad ni arrastra días de un año al siguiente.
