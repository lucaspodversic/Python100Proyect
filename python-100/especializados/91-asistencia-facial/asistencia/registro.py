"""Fichajes de entrada y salida en SQLite, con antirrebote e informe de horas.

* Cada persona alterna entre entrada y salida dentro del mismo día.
* Un nuevo reconocimiento dentro de ``antirrebote`` se ignora: la persona
  sigue frente a la cámara y no queremos diez fichajes por segundo.
* :meth:`Registro.purgar` aplica la política de retención (minimización de
  datos).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS fichajes (
    id INTEGER PRIMARY KEY,
    persona TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('entrada', 'salida')),
    momento TEXT NOT NULL,
    origen TEXT NOT NULL DEFAULT 'facial'   -- 'facial' o 'manual'
);
CREATE INDEX IF NOT EXISTS ix_persona_momento ON fichajes(persona, momento);
"""


@dataclass(frozen=True)
class Fichaje:
    """Un fichaje: persona, 'entrada' o 'salida', momento y origen ('facial' o 'manual')."""
    persona: str
    tipo: str
    momento: datetime
    origen: str = "facial"


class Registro:
    """Registro de fichajes en SQLite. Alterna entrada/salida por persona y día, aplica
    antirrebote, arma informes de horas y permite purgar por antigüedad y olvidar a una
    persona.
    """
    def __init__(self, ruta: str | Path = ":memory:", antirrebote: timedelta = timedelta(minutes=2)) -> None:
        """``:memory:`` por defecto (tests); ``antirrebote`` evita fichajes dobles si la
        persona sigue frente a la cámara.
        """
        self.db = sqlite3.connect(str(ruta))
        self.db.executescript(ESQUEMA)
        self.antirrebote = antirrebote

    def cerrar(self) -> None:
        """Cierra la conexión."""
        self.db.close()

    def ultimo(self, persona: str) -> Fichaje | None:
        """Último fichaje de la persona (desempata por id si hay dos en el mismo segundo)."""
        f = self.db.execute("SELECT persona, tipo, momento, origen FROM fichajes WHERE persona=? "
                            "ORDER BY momento DESC, id DESC LIMIT 1", (persona,)).fetchone()
        return Fichaje(f[0], f[1], datetime.fromisoformat(f[2]), f[3]) if f else None

    def marcar(self, persona: str, momento: datetime, origen: str = "facial") -> Fichaje | None:
        """Registra entrada o salida según el último fichaje. ``None`` si lo descarta el antirrebote."""
        previo = self.ultimo(persona)
        if previo and momento - previo.momento < self.antirrebote:
            return None
        # Un fichaje de otro día empieza siempre con entrada (salida olvidada).
        if previo and previo.tipo == "entrada" and previo.momento.date() == momento.date():
            tipo = "salida"
        else:
            tipo = "entrada"
        with self.db:
            self.db.execute("INSERT INTO fichajes(persona, tipo, momento, origen) VALUES (?,?,?,?)",
                            (persona, tipo, momento.isoformat(timespec="seconds"), origen))
        return Fichaje(persona, tipo, momento, origen)

    def del_dia(self, dia: date) -> list[Fichaje]:
        """Fichajes de un día, ordenados por persona y hora. Compara el prefijo de fecha del
        texto ISO.
        """
        filas = self.db.execute("SELECT persona, tipo, momento, origen FROM fichajes WHERE substr(momento,1,10)=? "
                                "ORDER BY persona, momento, id", (dia.isoformat(),)).fetchall()
        return [Fichaje(p, t, datetime.fromisoformat(m), o) for p, t, m, o in filas]

    def informe_dia(self, dia: date) -> dict[str, dict]:
        """Por persona: horas trabajadas y si quedó una entrada sin salida."""
        res: dict[str, dict] = {}
        for f in self.del_dia(dia):
            r = res.setdefault(f.persona, {"segundos": 0, "abierta": None, "fichajes": 0})
            r["fichajes"] += 1
            if f.tipo == "entrada":
                r["abierta"] = f.momento
            elif r["abierta"]:
                r["segundos"] += int((f.momento - r["abierta"]).total_seconds())
                r["abierta"] = None
        return {p: {"horas": round(r["segundos"] / 3600, 2), "sin_salida": r["abierta"] is not None,
                    "fichajes": r["fichajes"]} for p, r in res.items()}

    def purgar(self, antes_de: datetime) -> int:
        """Borra fichajes anteriores a ``antes_de`` (política de retención). Devuelve cuántos
        borró.
        """
        with self.db:
            return self.db.execute("DELETE FROM fichajes WHERE momento < ?",
                                   (antes_de.isoformat(timespec="seconds"),)).rowcount

    def olvidar(self, persona: str) -> int:
        """Borra todos los fichajes de una persona (derecho de supresión). Devuelve cuántos
        borró.
        """
        with self.db:
            return self.db.execute("DELETE FROM fichajes WHERE persona=?", (persona,)).rowcount
