"""Cifrado de la bóveda: **scrypt** (KDF) + **AES-256-GCM** (cifrado autenticado).

Formato del archivo (JSON):

.. code-block:: json

    {"formato": "boveda-py100", "version": 1,
     "kdf": {"nombre": "scrypt", "n": 131072, "r": 8, "p": 1, "sal": "<b64>"},
     "nonce": "<b64>", "datos": "<b64 ciphertext+tag>"}

* La clave se deriva de la contraseña maestra con scrypt (costoso en
  memoria → frena ataques con GPU). La sal es aleatoria por bóveda.
* AES-GCM autentica: si alguien altera un byte, o la contraseña es
  incorrecta, el descifrado falla (no hay "basura descifrada").
* La cabecera (sin ``datos``) se pasa como **AAD**: cambiar los parámetros
  del KDF o la versión también invalida el archivo.
* Cada guardado usa un nonce nuevo de 96 bits (nunca se reutiliza con la misma clave).
"""
from __future__ import annotations

import base64
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

FORMATO = "boveda-py100"
VERSION = 1


class ErrorBoveda(Exception):
    """Contraseña incorrecta, archivo alterado o formato inválido."""


@dataclass(frozen=True)
class ParametrosKdf:
    """Parámetros de scrypt. Por defecto ~128 MiB de memoria (recomendación OWASP: N≥2^17)."""

    n: int = 2**17
    r: int = 8
    p: int = 1

    def validar(self) -> None:
        """Rechaza parámetros de scrypt fuera de rango ANTES de derivar: n debe ser potencia de
        2 entre 2^10 y 2^20, r de 1 a 32 y p de 1 a 16. Como los parámetros vienen
        del archivo, sin este control un archivo manipulado podría pedir gigas de
        RAM (DoS) o bajar el costo para facilitar fuerza bruta.
        """
        # Límites para que un archivo malicioso no pida 64 GiB de RAM ni parámetros débiles.
        if not (2**10 <= self.n <= 2**20 and self.n & (self.n - 1) == 0 and 1 <= self.r <= 32 and 1 <= self.p <= 16):
            raise ErrorBoveda("parámetros de KDF fuera de rango")


def _b64(b: bytes) -> str:
    """Bytes → texto base64 (para guardar binarios dentro del JSON)."""
    return base64.b64encode(b).decode()


def _unb64(s: str) -> bytes:
    """Texto base64 → bytes. ``validate=True`` rechaza caracteres basura en vez de ignorarlos."""
    return base64.b64decode(s, validate=True)


def derivar_clave(maestra: str, sal: bytes, kdf: ParametrosKdf) -> bytes:
    """Deriva la clave AES de 256 bits a partir de la contraseña maestra con scrypt (costoso a
    propósito, en CPU y memoria, para frenar ataques de diccionario).
    """
    kdf.validar()
    return Scrypt(salt=sal, length=32, n=kdf.n, r=kdf.r, p=kdf.p).derive(maestra.encode("utf-8"))


def _cabecera(kdf: ParametrosKdf, sal: bytes, nonce: bytes) -> dict:
    """Cabecera en claro del archivo: formato, versión, parámetros de KDF, sal y nonce. Hace
    falta leerla antes de descifrar, así que no puede ir cifrada.
    """
    return {"formato": FORMATO, "version": VERSION,
            "kdf": {"nombre": "scrypt", "n": kdf.n, "r": kdf.r, "p": kdf.p, "sal": _b64(sal)},
            "nonce": _b64(nonce)}


def _aad(cabecera: dict) -> bytes:
    """Datos asociados (AAD) de AES-GCM: la cabecera serializada de forma canónica. GCM la
    autentica, así que cambiar un parámetro de la cabecera hace fallar el descifrado.
    """
    # JSON canónico (claves ordenadas, sin espacios) para que la AAD sea estable.
    return json.dumps(cabecera, sort_keys=True, separators=(",", ":")).encode()


class Cifrador:
    """Guarda la clave derivada en memoria mientras la bóveda está abierta.

    Así se puede volver a guardar sin pedir la contraseña ni repetir scrypt.
    La sal se mantiene; el nonce cambia en cada :meth:`cifrar`.
    """

    def __init__(self, clave: bytes, sal: bytes, kdf: ParametrosKdf) -> None:
        """Guarda la clave ya derivada (solo en memoria), la sal y los parámetros para poder
        volver a cifrar sin derivar de nuevo.
        """
        self._aes = AESGCM(clave)
        self.sal, self.kdf = sal, kdf

    @classmethod
    def nuevo(cls, maestra: str, kdf: ParametrosKdf = ParametrosKdf()) -> "Cifrador":
        """Cifrador para una bóveda nueva: sal aleatoria de 16 bytes y clave derivada de la
        maestra.
        """
        sal = os.urandom(16)
        return cls(derivar_clave(maestra, sal, kdf), sal, kdf)

    def cifrar(self, datos: dict) -> bytes:
        """Serializa ``datos`` a JSON y los cifra con AES-256-GCM. Usa un nonce NUEVO de 12
        bytes en cada guardado (repetir un nonce con la misma clave rompe GCM).
        """
        nonce = os.urandom(12)
        cab = _cabecera(self.kdf, self.sal, nonce)
        aad = _aad(cab)  # la cabecera queda autenticada (pero en claro)
        texto = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        cab["datos"] = _b64(self._aes.encrypt(nonce, texto, aad))
        return json.dumps(cab, indent=1).encode()

    @staticmethod
    def abrir(contenido: bytes, maestra: str) -> tuple["Cifrador", dict]:
        """Descifra; devuelve el cifrador (para guardar luego) y los datos."""
        try:
            cab = json.loads(contenido)
            if cab.get("formato") != FORMATO or cab.get("version") != VERSION:
                raise ErrorBoveda("formato o versión no soportados")
            k = cab["kdf"]
            if k.get("nombre") != "scrypt":
                raise ErrorBoveda("KDF no soportado")
            kdf = ParametrosKdf(int(k["n"]), int(k["r"]), int(k["p"]))
            sal, nonce, datos = _unb64(k["sal"]), _unb64(cab["nonce"]), _unb64(cab["datos"])
        except ErrorBoveda:
            raise
        except (ValueError, KeyError, TypeError) as e:
            raise ErrorBoveda("archivo de bóveda dañado") from e
        cifrador = Cifrador(derivar_clave(maestra, sal, kdf), sal, kdf)
        aad = _aad({kk: vv for kk, vv in cab.items() if kk != "datos"})
        try:
            texto = cifrador._aes.decrypt(nonce, datos, aad)
        except InvalidTag:
            # No se distingue "clave errónea" de "archivo alterado": ambos son fallo de autenticación.
            raise ErrorBoveda("contraseña maestra incorrecta o archivo alterado") from None
        return cifrador, json.loads(texto)


def escribir_atomico(ruta: Path, datos: bytes) -> None:
    """Temporal + fsync + ``os.replace``, con permisos 0600 (solo el dueño)."""
    fd, tmp = tempfile.mkstemp(dir=ruta.parent, prefix=f".{ruta.name}.")
    try:
        os.chmod(tmp, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(datos)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, ruta)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
