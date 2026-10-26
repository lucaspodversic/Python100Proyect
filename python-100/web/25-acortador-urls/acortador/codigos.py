"""Generación de códigos cortos y validación de URLs."""
from __future__ import annotations

import re
import secrets
from urllib.parse import urlsplit

# Alfabeto base62: dígitos + minúsculas + mayúsculas
# 62 símbolos válidos en una URL sin necesidad de escaparlos.
ALFABETO = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
# Alias de 3 a 32 caracteres: letras, dígitos, "_" y "-".
PATRON_ALIAS = re.compile(r"^[A-Za-z0-9_-]{3,32}$")
# Rutas propias del servicio que no pueden usarse como alias
# Si alguien usara "docs" como alias, taparía la documentación de FastAPI.
RESERVADOS = {"api", "docs", "redoc", "openapi", "stats", "health"}


# Base62 sirve para códigos secuenciales (id -> código). Se incluye como
# alternativa didáctica; la app usa códigos aleatorios (ver abajo).
def a_base62(n: int) -> str:
    """Convierte un entero no negativo a base62."""
    if n < 0:
        raise ValueError("n debe ser >= 0")
    if n == 0:
        return ALFABETO[0]
    digitos = []
    # Divisiones sucesivas por 62: cada resto es un dígito, del menos al más
    # significativo; por eso al final se invierte.
    while n:
        n, r = divmod(n, 62)
        digitos.append(ALFABETO[r])
    return "".join(reversed(digitos))


def desde_base62(s: str) -> int:
    """Operación inversa de `a_base62`."""
    n = 0
    for c in s:
        # Esquema de Horner: acumula dígito a dígito de izquierda a derecha.
        n = n * 62 + ALFABETO.index(c)
    return n


def codigo_aleatorio(largo: int = 7) -> str:
    """Código aleatorio criptográficamente seguro (62^7 ≈ 3,5 billones de combinaciones).

    Se prefiere aleatorio a secuencial para que no se puedan enumerar los
    enlaces de otros usuarios.
    """
    # secrets.choice usa el generador del sistema operativo (no predecible).
    return "".join(secrets.choice(ALFABETO) for _ in range(largo))


def validar_url(url: str) -> str:
    """Acepta solo URLs http/https absolutas con host. Devuelve la URL limpia.

    Bloquea esquemas peligrosos como `javascript:` o `data:`.
    """
    # Se toleran espacios accidentales al copiar/pegar.
    url = url.strip()
    partes = urlsplit(url)
    # Lista blanca de esquemas (no lista negra): todo lo que no sea http(s)
    # queda afuera, incluidos esquemas que hoy no conocemos. netloc vacío
    # descarta "http://" o "https:/ruta".
    if partes.scheme.lower() not in ("http", "https") or not partes.netloc:
        raise ValueError("Solo se aceptan URLs http(s) absolutas")
    if len(url) > 2048:
        raise ValueError("URL demasiado larga")
    return url


def validar_alias(alias: str) -> str:
    """Valida un alias personalizado."""
    # lower(): "DOCS" también se considera reservado.
    if not PATRON_ALIAS.match(alias) or alias.lower() in RESERVADOS:
        raise ValueError("Alias inválido o reservado")
    return alias
