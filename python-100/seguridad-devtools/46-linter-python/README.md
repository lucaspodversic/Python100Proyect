# 46 · Linter de código Python personalizado

Analizador estático que recorre el **AST** de tu código y detecta malas prácticas.

## Qué demuestra
- Uso del módulo `ast` (recorrido, nodos, posiciones).
- Arquitectura de **plugins por decorador** (`@regla`).
- Configuración por CLI o `[tool.linter]` en `pyproject.toml`, y supresión `# noqa`.

## Reglas
| Código | Descripción |
|---|---|
| L001 | `except:` sin tipo |
| L002 | argumento por defecto mutable |
| L003 | función demasiado larga (`max_lineas_funcion`, def. 50) |
| L004 | función/clase pública sin docstring |
| L005 | nombres fuera de PEP 8 |
| L006 | import no utilizado |
| L007 | línea larga (`max_largo_linea`, def. 100) |
| L008 | `== None` / `!= None` |
| L009 | `from x import *` |
| L010 | `print()` (preferir logging) |

## Arquitectura
```
linter/
  reglas.py  # Hallazgo, registro REGLAS, una función por regla
  motor.py   # analizar_codigo / analizar_rutas / noqa / config
  cli.py
```

## Instalación y uso
```bash
pip install -e ".[dev]"
python -m linter src/ --ignorar L010 --max-linea 120
python -m linter --listar
```
Config en `pyproject.toml`:
```toml
[tool.linter]
ignorar = ["L010"]
max_lineas_funcion = 40
```

## Tests
```bash
pytest
```

## Limitaciones
- Análisis sintáctico, no semántico (no infiere tipos ni resuelve imports).
- Para proyectos reales, `ruff` o `pylint` cubren cientos de reglas.
