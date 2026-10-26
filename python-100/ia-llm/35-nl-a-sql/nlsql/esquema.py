"""Introspección del esquema SQLite para dárselo como contexto al LLM."""
from __future__ import annotations

import sqlite3


def describir_esquema(con: sqlite3.Connection, ocultas: set[str] = frozenset(),
                      filas_ejemplo: int = 2) -> str:
    """Texto con tablas, columnas (tipo, PK), claves foráneas y filas de ejemplo.

    `ocultas`: columnas sensibles ("tabla.columna") que no se le muestran al
    LLM (y que el ejecutor además bloquea).
    """
    partes = []
    # Se excluyen las tablas internas sqlite_* (secuencias, estadísticas).
    tablas = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    for t in tablas:
        # table_info devuelve (cid, nombre, tipo, notnull, default, pk): c[1]
        # nombre, c[2] tipo, c[5] > 0 si es parte de la PK. El nombre de tabla
        # sale de sqlite_master (no del usuario) y va entre comillas dobles.
        cols = [c for c in con.execute(f'PRAGMA table_info("{t}")') if f"{t}.{c[1]}" not in ocultas]
        defs = [f"{c[1]} {c[2]}{' PK' if c[5] else ''}" for c in cols]
        # foreign_key_list: f[2] tabla destino, f[3] columna local, f[4] columna
        # destino. Las FK le dicen al LLM cómo hacer los JOIN.
        fks = sorted(f"{f[3]} -> {f[2]}.{f[4]}" for f in con.execute(f'PRAGMA foreign_key_list("{t}")'))
        linea = f"TABLE {t}({', '.join(defs)})"
        if fks:
            linea += f"  FK: {', '.join(fks)}"
        nombres = ", ".join(f'"{c[1]}"' for c in cols)
        # Filas de ejemplo: ayudan al LLM a ver formatos (fechas, mayúsculas).
        # Solo se piden las columnas visibles, así lo oculto tampoco aparece acá.
        ejemplos = con.execute(f'SELECT {nombres} FROM "{t}" LIMIT ?', (filas_ejemplo,)).fetchall()
        if ejemplos:
            linea += "\n  ejemplos: " + "; ".join(str(tuple(e)) for e in ejemplos)
        partes.append(linea)
    return "\n".join(partes)
