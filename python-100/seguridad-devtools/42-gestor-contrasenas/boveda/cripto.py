"""Primitivas criptográficas (todas de la librería `cryptography`).

- KDF: scrypt (memoria-dura) con sal aleatoria de 16 bytes.
- Cifrado: AES-256-GCM (confidencialidad + integridad) con nonce de 12 bytes.
Nunca implementamos cripto propia: sólo combinamos primitivas auditadas.

Formato del blob cifrado (bytes):
    MAGIC(4) | VERSION(1) | SAL(16) | NONCE(12) | CIFRADO+TAG(n)
El encabezado se pasa como "datos asociados" (AAD) a GCM, así que
cualquier alteración del encabezado también hace fallar el descifrado.
"""
from __future__ import annotations

import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

# Firma del formato: permite reconocer el archivo y rechazar otros rápidamente.
MAGIC = b"BVD1"
VERSION = 1
# 16 bytes de sal y 12 de nonce: tamaños recomendados para scrypt y AES-GCM respectivamente.
LARGO_SAL = 16
LARGO_NONCE = 12
# Parámetros de scrypt: n=2**15 es razonable para uso interactivo.
# En los tests se bajan para que corran rápido (ver parámetro `n`).
N_POR_DEFECTO = 2**15


class ErrorDescifrado(Exception):
    """Contraseña maestra incorrecta o datos alterados."""


def derivar_clave(maestra: str, sal: bytes, n: int = N_POR_DEFECTO) -> bytes:
    """Deriva una clave de 32 bytes (AES-256) desde la contraseña maestra."""
    # r=8, p=1: valores estándar. Memoria usada ≈ 128 · n · r bytes (32 MiB con n=2**15).
    kdf = Scrypt(salt=sal, length=32, n=n, r=8, p=1)
    return kdf.derive(maestra.encode("utf-8"))


def cifrar(datos: bytes, maestra: str, n: int = N_POR_DEFECTO) -> bytes:
    """Cifra `datos` con una clave derivada de `maestra` (sal y nonce nuevos)."""
    sal = os.urandom(LARGO_SAL)  # sal aleatoria por cada guardado
    nonce = os.urandom(LARGO_NONCE)  # nonce único: jamás se reutiliza con la misma clave
    # Guardamos log2(n) en el encabezado para poder descifrar con los mismos parámetros
    # n debe ser potencia de 2 (lo exige scrypt), así que log2(n) entra en un byte.
    encabezado = MAGIC + bytes([VERSION, n.bit_length() - 1]) + sal + nonce
    clave = derivar_clave(maestra, sal, n)
    # El resultado incluye el tag de autenticación de 16 bytes al final.
    cifrado = AESGCM(clave).encrypt(nonce, datos, encabezado)
    return encabezado + cifrado


def descifrar(blob: bytes, maestra: str) -> bytes:
    """Descifra un blob producido por `cifrar`. Lanza ErrorDescifrado si falla."""
    # Tamaño del encabezado: magic(4) + versión(1) + log2(n)(1) + sal + nonce = 34 bytes.
    largo_enc = len(MAGIC) + 2 + LARGO_SAL + LARGO_NONCE
    # Caso borde: archivos truncados o ajenos se rechazan antes de gastar tiempo en scrypt.
    if len(blob) < largo_enc + 16 or not blob.startswith(MAGIC):
        raise ErrorDescifrado("Formato de bóveda inválido")
    if blob[4] != VERSION:
        raise ErrorDescifrado("Versión no soportada")
    # Se recupera el costo usado al cifrar: bóvedas con distinto n se abren sin configuración extra.
    n = 2 ** blob[5]
    sal = blob[6:6 + LARGO_SAL]
    nonce = blob[6 + LARGO_SAL:largo_enc]
    clave = derivar_clave(maestra, sal, n)
    try:
        # El encabezado completo va como AAD: alterar la sal, el nonce o n también invalida el tag.
        return AESGCM(clave).decrypt(nonce, blob[largo_enc:], blob[:largo_enc])
    except InvalidTag as exc:
        # No distinguimos "clave mala" de "datos alterados" a propósito
        raise ErrorDescifrado("Contraseña maestra incorrecta o archivo alterado") from exc
