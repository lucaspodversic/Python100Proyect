"""Orquestación: pregunta -> prompt con esquema -> SQL -> validar -> ejecutar.

Si el SQL es inválido o falla al ejecutarse, se reintenta UNA vez pasándole
al LLM el error (auto-corrección), lo que mejora mucho la tasa de éxito.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from nlsql.ejecutor import ConsultaRechazada, ejecutar
from nlsql.esquema import describir_esquema
from nlsql.llm import Mensaje, ProveedorLLM
from nlsql.validador import SQLInvalido, extraer_sql, validar_select

SISTEMA = """Traducís preguntas en español a UNA consulta SQLite de solo lectura (SELECT).
Usá solo las tablas y columnas del esquema. Devolvé únicamente el SQL en un bloque ```sql```.
Esquema:
{esquema}"""


@dataclass
class Resultado:
    pregunta: str
    sql: str | None
    columnas: list[str] = field(default_factory=list)
    filas: list[tuple] = field(default_factory=list)
    error: str | None = None
    intentos: int = 0


class TraductorNLSQL:
    def __init__(self, con: sqlite3.Connection, llm: ProveedorLLM, ocultas: set[str] = frozenset(),
                 limite: int = 200, reintentos: int = 1) -> None:
        self.con, self.llm, self.ocultas = con, llm, set(ocultas)
        self.limite, self.reintentos = limite, reintentos
        # El esquema se calcula una vez (no cambia en una base de solo lectura).
        self.esquema = describir_esquema(con, self.ocultas)

    def preguntar(self, pregunta: str) -> Resultado:
        mensajes = [Mensaje("system", SISTEMA.format(esquema=self.esquema)), Mensaje("user", pregunta)]
        sql = None
        # reintentos=1 => intentos 1 y 2 (el original + una corrección).
        for intento in range(1, self.reintentos + 2):
            salida = self.llm.completar(mensajes)
            try:
                sql = validar_select(extraer_sql(salida), self.limite)
                cols, filas = ejecutar(self.con, sql, self.ocultas)
                return Resultado(pregunta, sql, cols, filas, intentos=intento)
            except (SQLInvalido, ConsultaRechazada, sqlite3.Error) as e:
                error = f"{type(e).__name__}: {e}"
                # Se agrega lo que respondió el LLM y el error, para que corrija con
                # contexto (patrón de auto-corrección).
                mensajes += [Mensaje("assistant", salida),
                             Mensaje("user", f"Ese SQL falló ({error}). Corregilo y devolvé solo el SQL.")]
        return Resultado(pregunta, sql, error=error, intentos=self.reintentos + 1)
