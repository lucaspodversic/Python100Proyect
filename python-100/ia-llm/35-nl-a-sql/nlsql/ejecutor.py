"""Ejecución en SOLO LECTURA con autorizador de SQLite y tiempo máximo."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

# Operaciones que el autorizador deja pasar: leer, seleccionar, llamar funciones.
PERMITIDAS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
# sqlite3.SQLITE_RECURSIVE existe desde 3.8.3: lo permitimos si está (para WITH RECURSIVE)
if hasattr(sqlite3, "SQLITE_RECURSIVE"):
    PERMITIDAS.add(sqlite3.SQLITE_RECURSIVE)
# Funciones que leen/escriben archivos o cargan código nativo: aunque sean
# "lecturas" para SQLite, darían acceso al sistema de archivos.
FUNCIONES_PROHIBIDAS = {"load_extension", "readfile", "writefile", "edit", "fts3_tokenizer"}


# La consulta era sintácticamente válida pero la política la prohíbe.
class ConsultaRechazada(PermissionError):
    pass


def conectar_solo_lectura(ruta: str | Path) -> sqlite3.Connection:
    """Abre la base con URI `mode=ro`: SQLite rechaza cualquier escritura."""
    # as_uri() escapa espacios y caracteres raros de la ruta (file:///...).
    uri = f"{Path(ruta).resolve().as_uri()}?mode=ro"
    return sqlite3.connect(uri, uri=True, check_same_thread=False)


def ejecutar(con: sqlite3.Connection, sql: str, ocultas: set[str] = frozenset(),
             segundos_max: float = 2.0) -> tuple[list[str], list[tuple]]:
    """Ejecuta con autorizador (por consulta) y corta consultas demasiado lentas."""
    # El autorizador no puede lanzar excepciones útiles: registra el motivo
    # acá y luego se arma un mensaje claro con él.
    bloqueos: list[str] = []

    # SQLite lo llama al COMPILAR la consulta, por cada operación: es la
    # defensa más fuerte porque mira lo que el motor realmente va a hacer,
    # no el texto. Para SQLITE_READ, arg1 = tabla y arg2 = columna.
    def autorizador(accion, arg1, arg2, _db, _trigger):
        if accion not in PERMITIDAS:
            bloqueos.append(f"acción {accion}")
            return sqlite3.SQLITE_DENY
        if accion == sqlite3.SQLITE_READ and f"{arg1}.{arg2}" in ocultas:
            bloqueos.append(f"columna {arg1}.{arg2}")
            return sqlite3.SQLITE_DENY
        if accion == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in FUNCIONES_PROHIBIDAS:
            bloqueos.append(f"función {arg2}")
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    # monotonic: no le afectan los cambios de hora del sistema.
    limite = time.monotonic() + segundos_max
    con.set_authorizer(autorizador)
    # El handler se llama cada N instrucciones de la VM; devolver != 0 aborta
    con.set_progress_handler(lambda: int(time.monotonic() > limite), 10_000)
    try:
        # fetchall dentro del try: el progress handler también corta mientras se
        # recorren las filas, no solo al preparar.
        cur = con.execute(sql)
        filas = cur.fetchall()
        return [d[0] for d in cur.description or []], filas
    except sqlite3.DatabaseError as e:
        if bloqueos:
            raise ConsultaRechazada(f"Bloqueado: {', '.join(bloqueos)}") from e
        # Cuando el progress handler aborta, SQLite lanza "interrupted".
        if "interrupted" in str(e):
            raise ConsultaRechazada("La consulta superó el tiempo máximo") from e
        raise
    finally:
        # Se limpian autorizador y handler: la conexión puede reutilizarse.
        con.set_authorizer(None)
        con.set_progress_handler(None, 0)
