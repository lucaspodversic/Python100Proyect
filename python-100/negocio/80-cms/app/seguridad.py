"""Utilidades de seguridad: contraseñas, tokens de sesión y roles.

- Contraseñas: PBKDF2-HMAC-SHA256 con sal aleatoria (solo librería estándar).
- Tokens: aleatorios (``secrets``); en la BD se guarda su SHA-256, de modo que
  una filtración de la tabla no permite suplantar sesiones.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

# Iteraciones de PBKDF2. Valor moderado para que los tests sean rápidos;
# en producción conviene subirlo (OWASP recomienda >= 600.000 para SHA-256).
ITERACIONES = 100_000


def hashear_password(password: str) -> str:
    """Devuelve ``iteraciones$sal_hex$hash_hex`` para guardar en la BD."""
    sal = secrets.token_bytes(16)
    derivado = hashlib.pbkdf2_hmac("sha256", password.encode(), sal, ITERACIONES)
    return f"{ITERACIONES}${sal.hex()}${derivado.hex()}"


def verificar_password(password: str, almacenado: str) -> bool:
    """Comprueba una contraseña contra el hash almacenado.

    Usa ``hmac.compare_digest`` (comparación en tiempo constante) para no
    filtrar información por diferencias de tiempo.
    """
    try:
        iter_txt, sal_hex, hash_hex = almacenado.split("$")
    except ValueError:
        return False
    derivado = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(sal_hex), int(iter_txt)
    )
    return hmac.compare_digest(derivado.hex(), hash_hex)


def nuevo_token() -> str:
    """Genera un token de sesión aleatorio, seguro para URLs."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """SHA-256 del token (lo que se persiste en la tabla ``tokens``)."""
    return hashlib.sha256(token.encode()).hexdigest()
