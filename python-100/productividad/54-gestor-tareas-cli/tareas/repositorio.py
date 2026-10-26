"""Persistencia en SQLite (archivo único, sin servidor).

Las etiquetas se guardan como texto separado por comas para mantener
el esquema simple; los filtros se aplican en Python.
"""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from .modelo import Prioridad, Tarea

# IF NOT EXISTS: se puede abrir una base existente sin perder datos. Fechas en ISO (TEXT), booleanos como 0/1.
ESQUEMA = """
CREATE TABLE IF NOT EXISTS tareas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL,
    prioridad INTEGER NOT NULL,
    vence TEXT,
    etiquetas TEXT NOT NULL DEFAULT '',
    hecha INTEGER NOT NULL DEFAULT 0
)"""


class Repositorio:
    """CRUD de tareas sobre una conexión SQLite."""
    def __init__(self, ruta: str | Path = ":memory:") -> None:
        # ":memory:" (por defecto) crea una base temporal, ideal para tests.
        self.con = sqlite3.connect(str(ruta))
        self.con.execute(ESQUEMA)

    @staticmethod
    # Convierte una fila (id, titulo, prioridad, vence, etiquetas, hecha) en Tarea.
    def _fila(f: tuple) -> Tarea:
        return Tarea(f[1], Prioridad(f[2]), date.fromisoformat(f[3]) if f[3] else None,
                     # filter(None, ...) descarta el "" que deja "".split(",") cuando no hay etiquetas.
                     set(filter(None, f[4].split(","))), bool(f[5]), f[0])

    def agregar(self, t: Tarea) -> Tarea:
        cur = self.con.execute(
            # Parámetros "?" (nunca f-strings) para evitar inyección SQL.
            "INSERT INTO tareas (titulo, prioridad, vence, etiquetas, hecha) VALUES (?,?,?,?,?)",
            (t.titulo, int(t.prioridad), t.vence.isoformat() if t.vence else None,
             ",".join(sorted(t.etiquetas)), int(t.hecha)))
        self.con.commit()
        # Se completa el id asignado por AUTOINCREMENT en el mismo objeto.
        t.id = cur.lastrowid
        return t

    def obtener(self, id_: int) -> Tarea:
        f = self.con.execute("SELECT * FROM tareas WHERE id=?", (id_,)).fetchone()
        # Caso borde: id inexistente.
        if f is None:
            raise KeyError(f"No existe la tarea {id_}")
        return self._fila(f)

    def actualizar(self, t: Tarea) -> None:
        # Así un UPDATE sobre un id inexistente no pasa en silencio.
        self.obtener(t.id)  # valida existencia
        self.con.execute(
            "UPDATE tareas SET titulo=?, prioridad=?, vence=?, etiquetas=?, hecha=? WHERE id=?",
            (t.titulo, int(t.prioridad), t.vence.isoformat() if t.vence else None,
             ",".join(sorted(t.etiquetas)), int(t.hecha), t.id))
        self.con.commit()

    def borrar(self, id_: int) -> None:
        # rowcount 0 = no había nada que borrar → error explícito.
        if self.con.execute("DELETE FROM tareas WHERE id=?", (id_,)).rowcount == 0:
            raise KeyError(f"No existe la tarea {id_}")
        self.con.commit()

    def listar(self, *, incluir_hechas: bool = False, etiqueta: str | None = None,
               prioridad_min: Prioridad | None = None, vencen_hasta: date | None = None) -> list[Tarea]:
        # Se trae todo y se filtra en Python: suficiente para una lista personal de tareas.
        ts = [self._fila(f) for f in self.con.execute("SELECT * FROM tareas")]
        if not incluir_hechas:
            ts = [t for t in ts if not t.hecha]
        if etiqueta:
            ts = [t for t in ts if etiqueta in t.etiquetas]
        if prioridad_min:
            ts = [t for t in ts if t.prioridad >= prioridad_min]
        # Las tareas sin fecha quedan fuera de este filtro.
        if vencen_hasta:
            ts = [t for t in ts if t.vence and t.vence <= vencen_hasta]
        return sorted(ts, key=Tarea.clave_orden)

    def limpiar_hechas(self) -> int:
        # Devuelve cuántas se borraron para informarlo.
        n = self.con.execute("DELETE FROM tareas WHERE hecha=1").rowcount
        self.con.commit()
        return n
