# 35 · Lenguaje natural → SQL (seguro)

## Qué demuestra
Un asistente que traduce preguntas en español a SQL con un LLM y lo ejecuta
**sin riesgo para la base**, con defensa en profundidad:

1. **Validador estático**: una sola sentencia, solo `SELECT`/`WITH … SELECT`,
   sin palabras de escritura/administración (ignorando strings y comentarios), y `LIMIT` automático.
2. **Autorizador de SQLite** (`set_authorizer`): solo lectura a nivel motor,
   bloquea columnas sensibles (p. ej. `clientes.password_hash`) y funciones peligrosas.
3. **Conexión `mode=ro`**: la base se abre en solo lectura por URI.
4. **Tiempo máximo** por consulta (`set_progress_handler`).

Además: introspección del esquema (con FKs y filas de ejemplo) como contexto, y
**auto-corrección**: si el SQL falla, se le devuelve el error al LLM una vez.

## Arquitectura
```
nlsql/esquema.py    -> describir_esquema()
nlsql/validador.py  -> extraer_sql(), validar_select()
nlsql/ejecutor.py   -> conectar_solo_lectura(), ejecutar() con autorizador y timeout
nlsql/traductor.py  -> TraductorNLSQL (prompt, validación, ejecución, reintento)
nlsql/demo.py       -> base de ejemplo
```

## Instalación
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Uso
```bash
python -m nlsql --demo demo.db
OPENAI_API_KEY=... LLM_PROVEEDOR=openai python -m nlsql demo.db "¿Qué cliente compró más yerba?"
```

## Tests
```bash
pytest   # LLM falso, base SQLite temporal, sin red
```

## Limitaciones
- El LLM puede generar SQL válido pero semánticamente incorrecto: conviene mostrar el SQL al usuario.
- Pensado para SQLite; en Postgres/MySQL la capa equivalente es un usuario de BD con permisos solo SELECT.
