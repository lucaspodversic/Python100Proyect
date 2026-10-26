"""Validación estática del SQL generado por el LLM.

Es la PRIMERA de tres capas de defensa:
1. Validador (acá): una sola sentencia, debe ser SELECT (o WITH ... SELECT),
   sin palabras clave de escritura/administración. Agrega LIMIT.
2. Autorizador de SQLite (ejecutor.py): solo permite operaciones de lectura
   y bloquea columnas sensibles. Es la defensa real, a nivel motor.
3. Conexión `mode=ro`: aunque todo lo anterior fallara, la base es de solo lectura.
"""
from __future__ import annotations

import re

# Lista negra de palabras clave: es la capa más débil (puede haber falsos
# positivos, p. ej. una columna llamada "replace"), por eso hay otras dos.
PROHIBIDAS = {"insert", "update", "delete", "drop", "alter", "create", "replace", "attach", "detach",
              "pragma", "vacuum", "reindex", "analyze", "begin", "commit", "rollback", "savepoint",
              "release", "load_extension", "truncate", "grant"}


class SQLInvalido(ValueError):
    pass


def _sin_literales_ni_comentarios(sql: str) -> str:
    """Reemplaza strings y comentarios por espacios para analizar solo la estructura.
    Evita falsos positivos (un nombre 'Drop' en un string) y trucos (';' en comentarios)."""
    # Alternativas: string con comillas simples ('' es una comilla escapada),
    # identificador con comillas dobles, comentario -- hasta fin de línea y
    # comentario /* ... */. Los comentarios se vuelven espacio; los strings, ''.
    patron = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"|--[^\n]*|/\*.*?\*/", re.S)
    return patron.sub(lambda m: " " if m.group(0)[0] in "-/" else "''", sql)


def extraer_sql(texto: str) -> str:
    """Saca el SQL de la respuesta del LLM (bloque ```sql``` o texto plano)."""
    # No codicioso (.+?): toma el primer bloque de código.
    m = re.search(r"```(?:sql)?\s*(.+?)```", texto, re.S | re.I)
    return (m.group(1) if m else texto).strip()


def validar_select(sql: str, limite: int = 200) -> str:
    """Devuelve el SQL normalizado (con LIMIT) o lanza SQLInvalido."""
    # Un ";" final es inofensivo y muy común: se quita antes de buscar otros.
    sql = sql.strip().rstrip(";").strip()
    if not sql:
        raise SQLInvalido("SQL vacío")
    estructura = _sin_literales_ni_comentarios(sql)
    # Un ";" en el medio (fuera de strings) = varias sentencias => rechazo.
    if ";" in estructura:
        raise SQLInvalido("Solo se permite UNA sentencia")
    # Se buscan palabras completas en la estructura (sin strings): "Drop" en
    # un literal no cuenta, pero un DROP real sí.
    palabras = set(re.findall(r"[a-z_]+", estructura.lower()))
    if prohibidas := palabras & PROHIBIDAS:
        raise SQLInvalido(f"Palabras no permitidas: {', '.join(sorted(prohibidas))}")
    inicio = estructura.lstrip().lower()
    if not (inicio.startswith("select") or inicio.startswith("with")):
        raise SQLInvalido("Debe ser una consulta SELECT")
    # Un WITH sin SELECT no puede ser lectura (un WITH ... DELETE ya lo
    # atrapó la lista de prohibidas).
    if inicio.startswith("with") and "select" not in palabras:
        raise SQLInvalido("El CTE debe terminar en SELECT")
    # LIMIT: si no hay uno al final, se envuelve la consulta (respeta ORDER BY interno)
    if not re.search(r"\blimit\s+\d+(\s*(offset|,)\s*\d+)?\s*$", estructura, re.I):
        # Envolver evita romper consultas con ORDER BY o UNION. int() asegura que
        # el límite sea un número y no texto inyectado.
        sql = f"SELECT * FROM ({sql}) LIMIT {int(limite)}"
    return sql
