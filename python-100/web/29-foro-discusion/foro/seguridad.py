"""Hash de contraseñas y tokens con la biblioteca estándar.

- Contraseñas: `hashlib.scrypt` (función de derivación costosa en memoria,
  resistente a fuerza bruta con GPU) con sal aleatoria de 16 bytes.
- Tokens de sesión: aleatorios de 32 bytes; en la base se guarda solo su
  SHA-256, así una filtración de la base no permite suplantar sesiones.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

# Parámetros de scrypt (n=2^14, r=8, p=1: valores recomendados para uso interactivo)
# n = costo de CPU/memoria (16 MiB con r=8), r = tamaño de bloque, p = paralelismo.
N, R, P = 2**14, 8, 1


def hashear_clave(clave: str) -> str:
    """Devuelve 'scrypt$<sal_hex>$<hash_hex>'."""
    # Sal única por usuario: dos claves iguales producen hashes distintos y las
    # tablas precalculadas (rainbow tables) no sirven.
    sal = secrets.token_bytes(16)
    h = hashlib.scrypt(clave.encode(), salt=sal, n=N, r=R, p=P, dklen=32)
    # Se guarda algoritmo y sal junto al hash: permite migrar de algoritmo a futuro.
    return f"scrypt${sal.hex()}${h.hex()}"


def verificar_clave(clave: str, guardado: str) -> bool:
    """Compara en tiempo constante la clave contra el hash guardado."""
    try:
        algoritmo, sal_hex, hash_hex = guardado.split("$")
    # Formato corrupto (no tiene 3 partes) => se rechaza en vez de explotar.
    except ValueError:
        return False
    if algoritmo != "scrypt":
        return False
    # Se recalcula con la MISMA sal y parámetros, y se compara.
    h = hashlib.scrypt(clave.encode(), salt=bytes.fromhex(sal_hex), n=N, r=R, p=P, dklen=32)
    # compare_digest no corta en el primer carácter distinto (evita timing attacks).
    return hmac.compare_digest(h.hex(), hash_hex)


def nuevo_token() -> str:
    # 32 bytes aleatorios => ~43 caracteres URL-safe; imposible de adivinar.
    return secrets.token_urlsafe(32)


def huella_token(token: str) -> str:
    """SHA-256 del token: es lo único que se persiste."""
    # Para tokens aleatorios largos alcanza un hash rápido (no hace falta
    # scrypt): no se pueden atacar por diccionario.
    return hashlib.sha256(token.encode()).hexdigest()
