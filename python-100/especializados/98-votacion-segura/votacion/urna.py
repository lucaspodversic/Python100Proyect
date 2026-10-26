"""Urna encadenada por hash ("blockchain" sin consenso, al estilo de un log de
transparencia).

Cada voto es un bloque ``{indice, serie, opcion, firma, previo, hash}`` donde::

    hash = SHA-256(JSON canónico de {indice, serie, opcion, firma, previo})

y ``previo`` es el hash del bloque anterior (64 ceros para el primero). Si
alguien modifica, borra o reordena un voto en la base, el hash de ese bloque
deja de coincidir o se rompe el enlace con el siguiente, y la auditoría lo
detecta. El hash del último bloque ("cabeza") resume TODA la urna: publicarlo
periódicamente (o imprimirlo en el acta) impide reescribir la historia
completa sin que se note.

Persistencia en SQLite (stdlib). La columna ``serie`` es UNIQUE: es la
segunda barrera contra el doble voto con la misma papeleta firmada.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from dataclasses import asdict, dataclass

GENESIS = "0" * 64  # "hash previo" del primer bloque


@dataclass(frozen=True)
class Bloque:
    indice: int
    serie: str    # número de serie aleatorio de la papeleta (hex), elegido por el votante
    opcion: str
    firma: str    # firma ciega descegada, en hex
    previo: str
    hash: str

    @staticmethod
    def calcular_hash(indice: int, serie: str, opcion: str, firma: str, previo: str) -> str:
        # JSON con claves ordenadas y sin espacios = representación canónica:
        # el mismo contenido produce siempre los mismos bytes y el mismo hash.
        datos = json.dumps({"indice": indice, "serie": serie, "opcion": opcion, "firma": firma, "previo": previo},
                           sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(datos.encode()).hexdigest()

    def a_dict(self) -> dict:
        return asdict(self)


class SerieRepetida(Exception):
    """Ya hay un voto con ese número de serie (intento de doble voto)."""


class Urna:
    def __init__(self, ruta: str = ":memory:") -> None:
        # check_same_thread=False porque FastAPI puede atender en otro hilo;
        # el lock serializa las escrituras para que dos votos simultáneos no
        # lean el mismo "previo" y bifurquen la cadena.
        self._db = sqlite3.connect(ruta, check_same_thread=False)
        self._lock = threading.Lock()
        self._db.execute("""CREATE TABLE IF NOT EXISTS bloques (
            indice INTEGER PRIMARY KEY, serie TEXT UNIQUE NOT NULL, opcion TEXT NOT NULL,
            firma TEXT NOT NULL, previo TEXT NOT NULL, hash TEXT NOT NULL)""")
        self._db.commit()

    def agregar(self, serie: str, opcion: str, firma: str) -> Bloque:
        with self._lock:
            ult = self._db.execute("SELECT indice, hash FROM bloques ORDER BY indice DESC LIMIT 1").fetchone()
            indice, previo = (ult[0] + 1, ult[1]) if ult else (0, GENESIS)
            h = Bloque.calcular_hash(indice, serie, opcion, firma, previo)
            try:
                self._db.execute("INSERT INTO bloques VALUES (?,?,?,?,?,?)", (indice, serie, opcion, firma, previo, h))
                self._db.commit()
            except sqlite3.IntegrityError as e:  # UNIQUE(serie) violado
                self._db.rollback()
                raise SerieRepetida(serie) from e
            return Bloque(indice, serie, opcion, firma, previo, h)

    def bloques(self) -> list[Bloque]:
        filas = self._db.execute("SELECT indice, serie, opcion, firma, previo, hash FROM bloques ORDER BY indice")
        return [Bloque(*f) for f in filas]

    def cabeza(self) -> str:
        """Hash del último bloque (o GENESIS si la urna está vacía)."""
        b = self.bloques()
        return b[-1].hash if b else GENESIS

    def verificar_cadena(self) -> list[str]:
        """Recorre la cadena y devuelve la lista de problemas (vacía = íntegra)."""
        problemas: list[str] = []
        previo = GENESIS
        for esperado, b in enumerate(self.bloques()):
            if b.indice != esperado:
                problemas.append(f"bloque {b.indice}: índice fuera de secuencia (se esperaba {esperado})")
            if b.previo != previo:
                problemas.append(f"bloque {b.indice}: enlace roto con el anterior")
            if Bloque.calcular_hash(b.indice, b.serie, b.opcion, b.firma, b.previo) != b.hash:
                problemas.append(f"bloque {b.indice}: hash no coincide (contenido alterado)")
            previo = b.hash
        return problemas

    def cerrar(self) -> None:
        self._db.close()
