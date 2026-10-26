# 76 · Gestor de proyectos (tipo Trello)

API REST con **FastAPI + SQLAlchemy + SQLite** organizada en tableros → listas → tarjetas. Tiene miembros con permisos **por tablero**, reordenamiento, asignaciones, filtros y un historial de actividad.

## Qué demuestra

- **Permisos por recurso** en lugar de roles globales: `lector < editor < duenio`. Una función central, `exigir()`, controla todas las rutas.
  - A quien no es miembro se le responde **404**, sin revelar que el tablero existe.
  - Un miembro con permiso insuficiente recibe **403**.
- **Orden estable sin huecos**: las posiciones se renumeran 0..n-1 al crear, mover o borrar. Las posiciones fuera de rango se acotan.
- Mover tarjetas entre listas solo dentro del mismo tablero.
- Solo se puede asignar una tarjeta a editores o dueños del tablero.
- Búsqueda combinable por etiqueta, asignado y vencidas. La fecha "hoy" es inyectable para los tests.
- Historial de actividad para auditoría.

## Arquitectura

```
app/
├── modelos.py   # Tablero, Miembro(permiso), Lista, Tarjeta, Actividad
├── servicio.py  # exigir(), mover_tarjeta/lista, asignar, vencidas
└── main.py      # rutas REST
```

Rutas principales:

- `POST /tableros`, `GET /tableros`, `GET|DELETE /tableros/{id}`
- `POST /tableros/{id}/miembros`, `POST /tableros/{id}/listas`
- `POST /listas/{id}/mover`, `POST /listas/{id}/tarjetas`
- `POST /tarjetas/{id}/mover`, `POST /tarjetas/{id}/asignar`, `DELETE /tarjetas/{id}`
- `GET /tableros/{id}/buscar?etiqueta=&asignado_id=&vencidas=`, `GET /tableros/{id}/actividad`

## Instalación y uso

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload   # documentación en /docs
```

## Tests

```bash
pytest
```

## Limitaciones

- Las posiciones son enteros que se renumeran. Con miles de tarjetas convendría usar índices fraccionarios (LexoRank).
- No hay tiempo real (WebSocket), comentarios ni adjuntos.
- Las ediciones simultáneas del orden siguen la regla "la última escritura gana".
