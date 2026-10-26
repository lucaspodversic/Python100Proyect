# 27 · Aplicación de reservas de citas

## Qué demuestra
Sistema de turnos para un negocio (peluquería, consultorio) con **FastAPI +
SQLite**: horarios semanales por profesional con varias franjas, servicios con
duración, cálculo de huecos en grilla de 15 min, **sin solapamientos**
(verificación bajo candado), anticipación mínima, y cancelación con código secreto.

## Arquitectura
```
reservas/agenda.py -> Agenda: franjas, huecos disponibles, reservar/cancelar (reloj inyectable)
reservas/app.py    -> FastAPI: disponibilidad, reservas, cancelación, agenda interna (X-Admin-Token)
tests/             -> tests del motor y de la API
```

## Instalación
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Uso
```bash
RESERVAS_DB=reservas.db RESERVAS_ADMIN_TOKEN=secreto uvicorn reservas.app:app
curl "localhost:8000/profesionales/ana/disponibles?servicio=corte&dia=2026-11-02"
curl -X POST localhost:8000/reservas -H 'content-type: application/json' \
  -d '{"profesional":"ana","servicio":"corte","inicio":"2026-11-02T09:00","cliente":"Lucas","email":"l@x.com"}'
```
Los horarios/servicios de ejemplo están en `HORARIOS_DEMO` y `SERVICIOS_DEMO`.

## Tests
```bash
pytest
```

## Limitaciones
- Horas locales del negocio sin zona horaria (un solo local).
- Sin feriados ni bloqueos puntuales; sin envío real de emails de confirmación.
