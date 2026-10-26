"""Capa de acceso a datos con SQLite (módulo estándar `sqlite3`).

Se usa un repositorio simple en lugar de un ORM para mantener el proyecto
liviano y que cada consulta SQL quede a la vista (con parámetros, nunca
concatenando strings, para evitar inyección SQL).
"""
from __future__ import annotations

import sqlite3
# threading.Lock: sqlite3 no es seguro si dos hilos usan la MISMA conexión a la vez.
import threading
from datetime import datetime, timezone
from typing import Any

# Esquema de la tabla de tareas. `prioridad` va de 1 (baja) a 3 (alta).
# IF NOT EXISTS hace que el esquema sea idempotente: abrir dos veces la misma
# base no falla ni borra datos. Las fechas se guardan como TEXT ISO 8601,
# que en SQLite se ordena correctamente de forma lexicográfica.
ESQUEMA = """
CREATE TABLE IF NOT EXISTS tareas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo      TEXT    NOT NULL,
    descripcion TEXT    NOT NULL DEFAULT '',
    completada  INTEGER NOT NULL DEFAULT 0,
    prioridad   INTEGER NOT NULL DEFAULT 2,
    vence       TEXT,
    creada      TEXT    NOT NULL,
    actualizada TEXT    NOT NULL
);
"""

# Campos que el cliente puede modificar (lista blanca para el UPDATE dinámico)
CAMPOS_EDITABLES = {"titulo", "descripcion", "completada", "prioridad", "vence"}


def _ahora() -> str:
    """Devuelve la fecha/hora actual en UTC con formato ISO 8601."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Patrón repositorio: la API nunca escribe SQL; si mañana se cambia SQLite por
# PostgreSQL, solo se reescribe esta clase.
class RepositorioTareas:
    """Encapsula todas las operaciones CRUD sobre la tabla `tareas`."""

    def __init__(self, ruta: str = ":memory:") -> None:
        # check_same_thread=False porque FastAPI puede atender en otro hilo;
        # protegemos el acceso concurrente con un candado.
        self._con = sqlite3.connect(ruta, check_same_thread=False)
        # row_factory=Row permite acceder a las columnas por nombre y convertir a dict.
        self._con.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        # executescript ejecuta varias sentencias juntas (acá solo el CREATE TABLE).
        with self._lock:
            self._con.executescript(ESQUEMA)

    @staticmethod
    def _a_dict(fila: sqlite3.Row) -> dict[str, Any]:
        """Convierte una fila SQLite en diccionario, con `completada` como bool."""
        d = dict(fila)
        # SQLite no tiene tipo booleano: se guarda 0/1 y se convierte al salir.
        d["completada"] = bool(d["completada"])
        return d

    def crear(self, titulo: str, descripcion: str = "", prioridad: int = 2,
              vence: str | None = None) -> dict[str, Any]:
        """Inserta una tarea nueva y la devuelve completa."""
        # Mismo timestamp para creada y actualizada en el alta.
        ts = _ahora()
        with self._lock:
            cur = self._con.execute(
                # Los "?" son parámetros: el driver escapa los valores, nunca se concatenan.
                "INSERT INTO tareas (titulo, descripcion, prioridad, vence, creada, actualizada)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (titulo, descripcion, prioridad, vence, ts, ts),
            )
            self._con.commit()
            # lastrowid es el id AUTOINCREMENT que SQLite asignó a la fila insertada.
            nuevo_id = cur.lastrowid
        # Se relee la fila para devolver también los valores por defecto de la base.
        return self.obtener(int(nuevo_id))  # type: ignore[return-value]

    def obtener(self, tarea_id: int) -> dict[str, Any] | None:
        """Devuelve una tarea por id o None si no existe."""
        with self._lock:
            fila = self._con.execute("SELECT * FROM tareas WHERE id = ?", (tarea_id,)).fetchone()
        return self._a_dict(fila) if fila else None

    def listar(self, completada: bool | None = None, buscar: str | None = None,
               orden: str = "id", limite: int = 50, desplazamiento: int = 0) -> list[dict[str, Any]]:
        """Lista tareas con filtros opcionales, orden y paginación."""
        # Se arma el WHERE de forma incremental: cada filtro agrega su condición y su
        # parámetro en el mismo orden, así los "?" y los valores siempre coinciden.
        condiciones: list[str] = []
        params: list[Any] = []
        if completada is not None:
            condiciones.append("completada = ?")
            # bool -> 0/1 porque así está guardado.
            params.append(int(completada))
        if buscar:
            # Búsqueda simple por subcadena en título o descripción
            condiciones.append("(titulo LIKE ? OR descripcion LIKE ?)")
            params += [f"%{buscar}%", f"%{buscar}%"]
        # Si no hay filtros, el WHERE queda vacío (se listan todas).
        where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
        # El orden se valida contra una lista blanca: no se puede parametrizar
        # un nombre de columna, así que nunca se inserta texto del usuario.
        # "vence IS NULL" vale 0 para las que tienen fecha y 1 para las que no:
        # así las tareas sin vencimiento quedan al final en vez de al principio.
        ordenes = {"id": "id ASC", "prioridad": "prioridad DESC, id ASC", "vence": "vence IS NULL, vence ASC"}
        sql = f"SELECT * FROM tareas {where} ORDER BY {ordenes.get(orden, 'id ASC')} LIMIT ? OFFSET ?"
        # LIMIT/OFFSET implementan la paginación (también parametrizados).
        params += [limite, desplazamiento]
        with self._lock:
            filas = self._con.execute(sql, params).fetchall()
        return [self._a_dict(f) for f in filas]

    def actualizar(self, tarea_id: int, cambios: dict[str, Any]) -> dict[str, Any] | None:
        """Aplica cambios parciales (PATCH). Ignora campos no permitidos."""
        # Lista blanca: aunque llegue "id" o "creada" en el pedido, se descarta.
        # Esto es clave porque los nombres de columna van al SQL con f-string.
        cambios = {k: v for k, v in cambios.items() if k in CAMPOS_EDITABLES}
        # Si no existe se devuelve None y la API lo traduce a 404.
        if not self.obtener(tarea_id):
            return None
        # Un PATCH vacío ({}) es válido: no toca nada y devuelve la tarea igual.
        if cambios:
            if "completada" in cambios:
                cambios["completada"] = int(bool(cambios["completada"]))
            # Ej.: {"titulo": .., "prioridad": ..} -> "titulo = ?, prioridad = ?"
            asignaciones = ", ".join(f"{k} = ?" for k in cambios)
            with self._lock:
                self._con.execute(
                    f"UPDATE tareas SET {asignaciones}, actualizada = ? WHERE id = ?",
                    (*cambios.values(), _ahora(), tarea_id),
                )
                self._con.commit()
        return self.obtener(tarea_id)

    def borrar(self, tarea_id: int) -> bool:
        """Borra una tarea. Devuelve True si existía."""
        with self._lock:
            cur = self._con.execute("DELETE FROM tareas WHERE id = ?", (tarea_id,))
            self._con.commit()
        # rowcount = filas afectadas por el DELETE: 0 significa que no existía.
        return cur.rowcount > 0

    def estadisticas(self) -> dict[str, int]:
        """Cuenta total, completadas y pendientes."""
        with self._lock:
            total, hechas = self._con.execute(
                # SUM sobre una tabla vacía da NULL; COALESCE lo convierte en 0.
                "SELECT COUNT(*), COALESCE(SUM(completada), 0) FROM tareas").fetchone()
        return {"total": total, "completadas": hechas, "pendientes": total - hechas}
