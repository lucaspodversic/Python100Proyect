"""Lógica central del comprobador (independiente de la red).

El flujo k-anonymity es:
1. Calcular SHA-1 de la contraseña (hex en mayúsculas).
2. Separar prefijo (5 caracteres) y sufijo (35 caracteres).
3. Pedir a la API todos los sufijos que comparten ese prefijo.
4. Buscar localmente nuestro sufijo en la respuesta.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol


class ClienteRango(Protocol):
    """Interfaz de cualquier cliente que sepa consultar un rango de hashes.

    Se define como Protocol para poder inyectar un fake en los tests
    sin hacer pedidos reales a internet.
    """

    # Único método requerido: cualquier objeto que lo tenga sirve (tipado estructural).
    def consultar_rango(self, prefijo: str) -> str:
        """Devuelve el texto crudo de la API: líneas 'SUFIJO:CONTEO'."""
        ...


@dataclass(frozen=True)
class ResultadoChequeo:
    """Resultado de comprobar una contraseña."""

    comprometida: bool  # True si aparece al menos una vez
    apariciones: int  # Cantidad de veces vista en filtraciones
    prefijo: str  # Prefijo enviado a la API (útil para auditar qué salió)


def sha1_mayusculas(contrasena: str) -> str:
    """Calcula el SHA-1 en hexadecimal mayúsculas (formato que usa HIBP)."""
    # SHA-1 NO se usa aquí como protección criptográfica, sólo como
    # identificador compatible con la base de datos de HIBP.
    return hashlib.sha1(contrasena.encode("utf-8")).hexdigest().upper()


def dividir_hash(hash_hex: str) -> tuple[str, str]:
    """Divide el hash en (prefijo de 5, sufijo de 35)."""
    # Caso borde: un hash truncado o de otro algoritmo (p. ej. SHA-256 de 64) se rechaza.
    if len(hash_hex) != 40:
        raise ValueError("Se esperaba un SHA-1 hexadecimal de 40 caracteres")
    # 16^5 ≈ 1 millón de prefijos posibles: cada uno agrupa cientos de hashes, así la API no sabe cuál es el nuestro.
    return hash_hex[:5], hash_hex[5:]


def buscar_sufijo(respuesta: str, sufijo: str) -> int:
    """Busca el sufijo en la respuesta de la API y devuelve el conteo.

    La API devuelve líneas con formato 'SUFIJO:CONTEO'. Con el
    encabezado 'Add-Padding' puede incluir entradas de relleno con
    conteo 0, que tratamos como "no encontrada".
    """
    # Recorrido lineal: la respuesta trae unos ~800 sufijos, no hace falta indexar.
    for linea in respuesta.splitlines():
        # strip() quita el "\r" de los finales CRLF que usa la API.
        linea = linea.strip()
        if not linea or ":" not in linea:
            continue  # Ignoramos líneas vacías o malformadas
        # partition divide sólo en el primer ':' y nunca falla aunque falte el separador.
        suf, _, conteo = linea.partition(":")
        # Comparación sin distinguir mayúsculas: el sufijo puede llegar en minúsculas.
        if suf.upper() == sufijo.upper():
            try:
                return int(conteo)
            except ValueError:
                # Conteo no numérico (respuesta corrupta): se trata como no encontrada en vez de romper.
                return 0
    # El sufijo no está en el rango: la contraseña no figura en filtraciones conocidas.
    return 0


def comprobar(contrasena: str, cliente: ClienteRango) -> ResultadoChequeo:
    """Comprueba una contraseña usando el cliente inyectado."""
    # Caso borde: la cadena vacía no es una contraseña; mejor avisar que consultar su hash.
    if not contrasena:
        raise ValueError("La contraseña no puede estar vacía")
    prefijo, sufijo = dividir_hash(sha1_mayusculas(contrasena))
    respuesta = cliente.consultar_rango(prefijo)  # Sólo sale el prefijo
    # La comparación se hace localmente: el sufijo nunca sale de esta máquina.
    conteo = buscar_sufijo(respuesta, sufijo)
    return ResultadoChequeo(comprometida=conteo > 0, apariciones=conteo, prefijo=prefijo)
