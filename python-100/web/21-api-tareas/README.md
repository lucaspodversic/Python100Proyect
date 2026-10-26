# 21 · API REST de gestión de tareas (To-Do)

## Qué demuestra
Un backend CRUD completo con **FastAPI**: validación con Pydantic, códigos HTTP
correctos (201/204/404/422), filtros, búsqueda, ordenamiento con lista blanca,
paginación y persistencia en **SQLite** con consultas parametrizadas.

## Arquitectura
```
app/
  db.py    -> RepositorioTareas: SQL con sqlite3, candado para concurrencia
  main.py  -> crear_app(): fábrica FastAPI, modelos Pydantic y endpoints
tests/
  test_api.py -> tests end-to-end con TestClient
```
La fábrica `crear_app(ruta_db)` permite inyectar una base en memoria en los tests.

## Instalación
```bash
python -m venv .venv && source .venv/bin/activate   # (Windows: .venv\Scripts\activate)
pip install -e ".[dev]"
```

## Uso
```bash
TAREAS_DB=tareas.db uvicorn app.main:app --reload
# Documentación interactiva: http://127.0.0.1:8000/docs
curl -X POST localhost:8000/tareas -H 'content-type: application/json' -d '{"titulo":"Comprar pan","prioridad":3}'
curl "localhost:8000/tareas?completada=false&orden=prioridad"
```

## Tests
```bash
pytest
```

## Limitaciones
- Sin autenticación (es una API de demostración de CRUD; ver proyecto 29 para auth).
- SQLite con una sola conexión: adecuado para uso personal, no para alta concurrencia.
