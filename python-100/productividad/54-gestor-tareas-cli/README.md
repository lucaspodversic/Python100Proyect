# 54 · Gestor de tareas en terminal

Agregá, listá y completá tareas con prioridades, fechas límite y etiquetas,
guardadas en un archivo SQLite.

## Qué demuestra
- Separación dominio (`modelo`) / persistencia (`repositorio`) / interfaz (`cli`).
- SQLite de la librería estándar con consultas parametrizadas.
- Fechas "humanas": `hoy`, `mañana`, `+3`, `viernes`, `2026-12-24`.
- Orden útil: pendientes → fecha más cercana → prioridad alta.

## Arquitectura
```
tareas/
  modelo.py       # Tarea, Prioridad, parsear_fecha
  repositorio.py  # Repositorio (SQLite)
  cli.py          # subcomandos argparse
```

## Instalación y uso
```bash
pip install -e ".[dev]"
python -m tareas agregar "Pagar luz" -p alta -v viernes -e casa
python -m tareas listar                   # pendientes
python -m tareas listar --todas -e casa
python -m tareas listar --hasta +7        # vencen esta semana
python -m tareas hecha 1
python -m tareas editar 2 -v - --titulo "Nuevo título"   # '-' quita la fecha
python -m tareas limpiar
```
La base por defecto es `~/.tareas.db` (o `--db` / variable `TAREAS_DB`).

## Tests
```bash
pytest
```

## Limitaciones
- Sin recordatorios ni sincronización; un único usuario local.
