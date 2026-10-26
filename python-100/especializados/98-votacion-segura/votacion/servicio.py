"""Reglas de la elección, sin HTTP (testeable directo).

Flujo completo:

1. **Padrón**: la administración registra a cada votante habilitado y le
   entrega (por un canal privado, p. ej. en mano) un **token de un solo uso**.
   Guardamos solo el SHA-256 del token: si se filtra la base, los tokens no
   sirven.
2. **Firma** (canal identificado): el votante presenta su token y un valor
   cegado. Si el token es válido y no se usó, se marca usado y se devuelve la
   firma cegada. → *una persona, una firma*.
3. **Voto** (canal anónimo, p. ej. Tor o un mixnet): el votante envía
   ``(serie, opción, firma)``. Se verifica la firma sobre el mensaje canónico
   y que la serie no se haya usado. → *una firma, un voto*.
4. **Auditoría**: cualquiera puede descargar la urna, recalcular la cadena,
   verificar cada firma con la clave pública y recontar.

Anonimato: el paso 2 conoce a la persona pero solo ve un número aleatorio;
el paso 3 ve el voto pero no a la persona. Nada en la base vincula ambos.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import threading
from collections import Counter
from enum import Enum

from .cripto import Autoridad, ClavePublica, verificar
from .urna import SerieRepetida, Urna


class Estado(str, Enum):
    PREPARACION = "preparacion"   # se carga el padrón; aún no se firma ni se vota
    ABIERTA = "abierta"           # se emiten firmas y se reciben votos
    CERRADA = "cerrada"           # solo lectura: resultados y auditoría


class ErrorVotacion(Exception):
    """Error de negocio; ``codigo`` se traduce a un status HTTP en la API."""

    def __init__(self, mensaje: str, codigo: int = 400) -> None:
        super().__init__(mensaje)
        self.codigo = codigo


def mensaje_papeleta(eleccion: str, serie: str, opcion: str) -> bytes:
    """Mensaje canónico que se firma: liga la firma a la elección, la serie Y la opción.

    Si solo se firmara la serie, quien intercepte el voto podría cambiar la
    opción manteniendo la firma válida. Con este formato, cambiar cualquier
    campo invalida la firma.
    """
    # "\x1f" (separador de unidad ASCII) no puede aparecer en los campos validados.
    return "\x1f".join(("papeleta", eleccion, serie, opcion)).encode()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Eleccion:
    def __init__(self, id_: str, opciones: list[str], autoridad: Autoridad | None = None, ruta_db: str = ":memory:",
                 bits: int = 2048) -> None:
        # Validamos opciones: no vacías, sin duplicados, sin el carácter separador.
        if len(opciones) < 2 or len(set(opciones)) != len(opciones) or any(not o or "\x1f" in o for o in opciones):
            raise ValueError("se necesitan al menos 2 opciones distintas y no vacías")
        self.id, self.opciones = id_, list(opciones)
        self.autoridad = autoridad or Autoridad(bits)
        self.estado = Estado.PREPARACION
        self.urna = Urna(ruta_db)
        # El padrón vive en la MISMA base pero en otra tabla sin relación con los votos.
        self._db = self.urna._db
        self._lock = threading.Lock()
        self._db.execute("""CREATE TABLE IF NOT EXISTS padron (
            votante TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, usado INTEGER NOT NULL DEFAULT 0)""")
        self._db.commit()

    @property
    def publica(self) -> ClavePublica:
        return self.autoridad.publica

    # ---------- administración ----------
    def registrar(self, votante: str) -> str:
        """Agrega al padrón y devuelve el token EN CLARO (única vez que existe fuera del votante)."""
        if self.estado is Estado.CERRADA:
            raise ErrorVotacion("la elección está cerrada", 409)
        token = secrets.token_urlsafe(24)  # 192 bits de entropía
        try:
            self._db.execute("INSERT INTO padron (votante, token_hash) VALUES (?, ?)", (votante, _hash_token(token)))
            self._db.commit()
        except sqlite3.IntegrityError as e:
            raise ErrorVotacion(f"{votante} ya está en el padrón", 409) from e
        return token

    def abrir(self) -> None:
        if self.estado is not Estado.PREPARACION:
            raise ErrorVotacion("solo se puede abrir una elección en preparación", 409)
        self.estado = Estado.ABIERTA

    def cerrar(self) -> None:
        if self.estado is not Estado.ABIERTA:
            raise ErrorVotacion("solo se puede cerrar una elección abierta", 409)
        self.estado = Estado.CERRADA

    # ---------- paso 2: firma ciega ----------
    def firmar(self, token: str, cegado: int) -> int:
        if self.estado is not Estado.ABIERTA:
            raise ErrorVotacion("la elección no está abierta", 409)
        h = _hash_token(token)
        with self._lock:  # evita que dos pedidos simultáneos con el mismo token obtengan 2 firmas
            fila = self._db.execute("SELECT usado FROM padron WHERE token_hash = ?", (h,)).fetchone()
            if fila is None:
                raise ErrorVotacion("token inválido", 401)
            if fila[0]:
                raise ErrorVotacion("token ya utilizado", 409)
            try:
                firma = self.autoridad.firmar_cegado(cegado)
            except ValueError as e:
                raise ErrorVotacion(str(e), 422) from e
            # Se marca usado DESPUÉS de firmar con éxito: un valor inválido no quema el token.
            self._db.execute("UPDATE padron SET usado = 1 WHERE token_hash = ?", (h,))
            self._db.commit()
        return firma

    # ---------- paso 3: voto anónimo ----------
    def votar(self, serie: str, opcion: str, firma: int) -> dict:
        if self.estado is not Estado.ABIERTA:
            raise ErrorVotacion("la elección no está abierta", 409)
        if opcion not in self.opciones:
            raise ErrorVotacion("opción inexistente", 422)
        # La serie la genera el votante: 32 bytes aleatorios en hex (64 caracteres).
        if len(serie) != 64 or any(c not in "0123456789abcdef" for c in serie):
            raise ErrorVotacion("serie inválida (se esperan 64 hex en minúscula)", 422)
        if not verificar(self.publica, mensaje_papeleta(self.id, serie, opcion), firma):
            raise ErrorVotacion("firma inválida", 403)
        try:
            b = self.urna.agregar(serie, opcion, format(firma, "x"))
        except SerieRepetida as e:
            raise ErrorVotacion("esta papeleta ya fue depositada", 409) from e
        # El "recibo" permite al votante comprobar luego que su voto está en la urna publicada.
        return {"indice": b.indice, "hash": b.hash}

    # ---------- paso 4: resultados y auditoría ----------
    def resultados(self) -> dict[str, int]:
        if self.estado is not Estado.CERRADA:
            # No publicamos parciales para no influir en quienes aún no votaron.
            raise ErrorVotacion("los resultados se publican al cerrar", 409)
        c = Counter(b.opcion for b in self.urna.bloques())
        return {o: c.get(o, 0) for o in self.opciones}

    def auditar(self) -> dict:
        """Verificación completa: cadena + firma de cada voto + coherencia con el padrón."""
        bloques = self.urna.bloques()
        problemas = self.urna.verificar_cadena()
        for b in bloques:
            if not verificar(self.publica, mensaje_papeleta(self.id, b.serie, b.opcion), int(b.firma, 16)):
                problemas.append(f"bloque {b.indice}: firma inválida")
        emitidas = self._db.execute("SELECT COUNT(*) FROM padron WHERE usado = 1").fetchone()[0]
        habilitados = self._db.execute("SELECT COUNT(*) FROM padron").fetchone()[0]
        # Puede haber menos votos que firmas (alguien pidió firma y no votó), nunca más.
        if len(bloques) > emitidas:
            problemas.append(f"hay {len(bloques)} votos pero solo {emitidas} firmas emitidas")
        return {
            "eleccion": self.id, "estado": self.estado.value, "clave_publica": {"n": str(self.publica.n), "e": self.publica.e,
                                                                               "huella": self.publica.huella()},
            "habilitados": habilitados, "firmas_emitidas": emitidas, "votos": len(bloques),
            "cabeza": self.urna.cabeza(), "integra": not problemas, "problemas": problemas,
            "bloques": [b.a_dict() for b in bloques],
        }


def tokens_iguales(a: str, b: str) -> bool:
    """Comparación en tiempo constante (evita ataques de temporización sobre el token de admin)."""
    return hmac.compare_digest(a.encode(), b.encode())
