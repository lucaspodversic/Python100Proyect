"""Cifrado de archivos por bloques (streaming) con AES-256-GCM.

Para no cargar archivos enormes en memoria, se cifran bloques de 64 KiB.
Cada bloque es un mensaje AES-GCM independiente con:
  - nonce = prefijo aleatorio (7 bytes) | contador (4 bytes) | bandera final (1 byte)
  - AAD   = encabezado completo del archivo
La bandera "final" en el nonce impide truncar el archivo (eliminar
bloques del final) sin ser detectado, y el contador impide reordenarlos.
Es la construcción "STREAM" (Hoang et al.) usando sólo primitivas de
la librería `cryptography`; no hay criptografía casera.

Formato:
  MAGIC "AESF" | versión(1) | log2(n scrypt)(1) | sal(16) | prefijo_nonce(7) | bloques...
  cada bloque cifrado = hasta 64 KiB + 16 bytes de tag
"""
from __future__ import annotations

import os
import struct
from pathlib import Path
from typing import BinaryIO

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"AESF"
VERSION = 1
# 64 KiB por bloque: memoria acotada y sobrecarga de tags despreciable (16 bytes cada 64 KiB).
TAM_BLOQUE = 64 * 1024
TAG = 16
# Costo de scrypt (memoria ≈ 128·n·r = 32 MiB): caro para un atacante, aceptable para un usuario.
N_POR_DEFECTO = 2**15
# magic(4) + versión(1) + log2(n)(1) + sal(16) + prefijo de nonce(7) = 29 bytes.
LARGO_ENCABEZADO = 4 + 1 + 1 + 16 + 7


class ErrorCifrado(Exception):
    """Contraseña incorrecta, archivo dañado, truncado o manipulado."""


def _clave(contrasena: str, sal: bytes, n: int) -> bytes:
    """Deriva 32 bytes con scrypt (resistente a fuerza bruta con GPU)."""
    return Scrypt(salt=sal, length=32, n=n, r=8, p=1).derive(contrasena.encode("utf-8"))


def _nonce(prefijo: bytes, contador: int, final: bool) -> bytes:
    """Construye el nonce de 12 bytes para el bloque `contador`."""
    # El contador ocupa 4 bytes: más de 2**32 bloques (256 TiB) repetiría nonces, algo inaceptable en GCM.
    if contador >= 2**32:
        raise ErrorCifrado("Archivo demasiado grande")
    # ">I" = entero sin signo de 4 bytes big-endian; 7 + 4 + 1 = 12 bytes, el nonce estándar de GCM.
    return prefijo + struct.pack(">I", contador) + (b"\x01" if final else b"\x00")


def _leer_completo(f: BinaryIO, n: int) -> bytes:
    """Lee exactamente n bytes salvo EOF (read() puede devolver menos)."""
    # Se acumula hasta completar n bytes: pipes y sockets pueden devolver lecturas parciales.
    partes, falta = [], n
    while falta:
        b = f.read(falta)
        # EOF: se devuelve lo que se haya leído (puede ser menos de n o nada).
        if not b:
            break
        partes.append(b); falta -= len(b)
    return b"".join(partes)


def cifrar_flujo(entrada: BinaryIO, salida: BinaryIO, contrasena: str, n: int = N_POR_DEFECTO,
                 tam_bloque: int = TAM_BLOQUE) -> int:
    """Cifra de `entrada` a `salida`. Devuelve la cantidad de bloques."""
    # Sal y prefijo nuevos por archivo: clave y nonces nunca se repiten entre archivos.
    sal, prefijo = os.urandom(16), os.urandom(7)
    # El costo de scrypt viaja en el encabezado para poder descifrar con los mismos parámetros.
    enc = MAGIC + bytes([VERSION, n.bit_length() - 1]) + sal + prefijo
    salida.write(enc)
    aes = AESGCM(_clave(contrasena, sal, n))
    contador = 0
    # Caso borde: con entrada vacía `actual` es b"" y se emite un único bloque final con sólo el tag.
    actual = _leer_completo(entrada, tam_bloque)
    while True:
        # Leemos por adelantado para saber si el bloque actual es el último
        siguiente = _leer_completo(entrada, tam_bloque)
        # Si no queda nada por leer, este es el último bloque y se marca en el nonce.
        final = not siguiente
        # Encabezado como AAD: alterar sal, n o prefijo hace fallar todos los bloques.
        salida.write(aes.encrypt(_nonce(prefijo, contador, final), actual, enc))
        contador += 1
        if final:
            return contador
        actual = siguiente


def descifrar_flujo(entrada: BinaryIO, salida: BinaryIO, contrasena: str,
                    tam_bloque: int = TAM_BLOQUE) -> int:
    """Descifra; lanza ErrorCifrado ante cualquier problema de integridad.

    Importante: si falla a mitad, la salida parcial NO es confiable;
    `descifrar_archivo` escribe en un temporal y sólo lo publica si todo verificó.
    """
    enc = _leer_completo(entrada, LARGO_ENCABEZADO)
    # Validación barata antes de gastar tiempo y memoria en scrypt.
    if len(enc) != LARGO_ENCABEZADO or not enc.startswith(MAGIC) or enc[4] != VERSION:
        raise ErrorCifrado("No es un archivo cifrado válido")
    # Offsets: [4]=versión, [5]=log2(n), [6:22]=sal, [22:29]=prefijo.
    n, sal, prefijo = 2 ** enc[5], enc[6:22], enc[22:29]
    aes = AESGCM(_clave(contrasena, sal, n))
    contador = 0
    # Cada bloque cifrado ocupa hasta tam_bloque + 16 bytes de tag.
    actual = _leer_completo(entrada, tam_bloque + TAG)
    # Caso borde: sólo encabezado sin bloques (todo archivo válido tiene al menos el bloque final).
    if not actual:
        raise ErrorCifrado("Archivo truncado")
    while True:
        siguiente = _leer_completo(entrada, tam_bloque + TAG)
        # Si se borraron bloques del final, el último presente se cifró con final=0 y aquí se prueba con
        # final=1: el tag no coincide y el truncamiento queda detectado.
        final = not siguiente
        try:
            salida.write(aes.decrypt(_nonce(prefijo, contador, final), actual, enc))
        except InvalidTag as exc:
            # GCM no distingue clave mala de datos alterados: el mensaje cubre ambos casos.
            raise ErrorCifrado("Contraseña incorrecta o archivo manipulado/truncado") from exc
        contador += 1
        if final:
            return contador
        actual = siguiente


def cifrar_archivo(origen: Path, destino: Path, contrasena: str, n: int = N_POR_DEFECTO) -> None:
    """Cifra un archivo en disco (no sobrescribe el destino si existe)."""
    # Nunca se sobrescribe: el destino podría ser otro archivo valioso.
    if Path(destino).exists():
        raise FileExistsError(destino)
    # "xb" = crear en exclusiva: falla también si el destino aparece entre la comprobación y la apertura.
    with open(origen, "rb") as fi, open(destino, "xb") as fo:
        cifrar_flujo(fi, fo, contrasena, n)


def descifrar_archivo(origen: Path, destino: Path, contrasena: str) -> None:
    """Descifra a un temporal y lo renombra sólo si toda la verificación pasó."""
    destino = Path(destino)
    if destino.exists():
        raise FileExistsError(destino)
    # El texto plano se escribe primero a ".parcial": un fallo a mitad no deja un archivo "válido" a medias.
    tmp = destino.with_name(destino.name + ".parcial")
    try:
        with open(origen, "rb") as fi, open(tmp, "wb") as fo:
            descifrar_flujo(fi, fo, contrasena)
        # Sólo se publica si todos los bloques verificaron.
        os.replace(tmp, destino)
    finally:
        if tmp.exists():
            tmp.unlink()  # nunca dejamos texto plano no verificado
