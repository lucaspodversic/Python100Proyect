"""Historial de precios en SQLite (permite ver tendencias y evitar alertas repetidas)."""

from __future__ import annotations

import sqlite3
import time


class Historial:
    def __init__(self, ruta: str = ":memory:") -> None:
        # ":memory:" por defecto para tests; la CLI pasa un archivo.
        self.db = sqlite3.connect(ruta)
        # El índice (clave, ts) acelera MIN(...) WHERE clave=? AND ts<? a medida que crece la tabla.
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS precios (clave TEXT, ts REAL, precio REAL, moneda TEXT, vuelo TEXT);
            CREATE TABLE IF NOT EXISTS alertas (clave TEXT, ts REAL, precio REAL);
            CREATE INDEX IF NOT EXISTS ix_precios ON precios(clave, ts);
        """)

    def registrar(self, clave: str, precio: float, moneda: str, vuelo: str, ts: float | None = None) -> None:
        # Parámetros "?" (nunca f-strings) y commit inmediato: si el proceso muere no se pierde la lectura.
        self.db.execute("INSERT INTO precios VALUES (?,?,?,?,?)", (clave, ts or time.time(), precio, moneda, vuelo))
        self.db.commit()

    def minimo_previo(self, clave: str, antes_de: float) -> float | None:
        """Mínimo histórico registrado ANTES de ``antes_de`` (excluye la lectura actual)."""
        # ts < antes_de (estricto): la lectura que se acaba de registrar no se compara consigo misma.
        # Sin filas, MIN devuelve NULL → None.
        return self.db.execute("SELECT MIN(precio) FROM precios WHERE clave=? AND ts<?", (clave, antes_de)).fetchone()[0]

    def serie(self, clave: str) -> list[tuple[float, float]]:
        return self.db.execute("SELECT ts, precio FROM precios WHERE clave=? ORDER BY ts", (clave,)).fetchall()

    def ultima_alerta(self, clave: str) -> float | None:
        # Precio de la alerta más reciente: base del anti-spam.
        fila = self.db.execute("SELECT precio FROM alertas WHERE clave=? ORDER BY ts DESC LIMIT 1", (clave,)).fetchone()
        return fila[0] if fila else None

    def guardar_alerta(self, clave: str, precio: float, ts: float | None = None) -> None:
        self.db.execute("INSERT INTO alertas VALUES (?,?,?)", (clave, ts or time.time(), precio))
        self.db.commit()
