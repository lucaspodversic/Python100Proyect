"""Cliente HTTP real para la API Pwned Passwords (sólo stdlib).

No se usa en los tests: allí se inyecta un fake. La URL base es
configurable para poder apuntar a un servidor local si hiciera falta.
"""
from __future__ import annotations

import re
import urllib.request

# Endpoint del rango: se le concatena el prefijo de 5 caracteres (sin clave de API: es gratuito).
URL_BASE = "https://api.pwnedpasswords.com/range/"
# User-Agent honesto: HIBP exige identificar la aplicación
USER_AGENT = "pwncheck-educativo/1.0 (+https://github.com/)"


class ClienteHIBP:
    """Implementación de ClienteRango que hace el pedido HTTPS real."""

    # timeout evita que la CLI quede colgada si la red no responde.
    def __init__(self, url_base: str = URL_BASE, timeout: float = 10.0) -> None:
        self.url_base = url_base
        self.timeout = timeout

    def consultar_rango(self, prefijo: str) -> str:
        # Validamos que el prefijo sea hex de 5 caracteres antes de salir a la red
        if not re.fullmatch(r"[0-9A-Fa-f]{5}", prefijo):
            raise ValueError("Prefijo inválido")
        # Add-Padding: la API agrega entradas falsas (conteo 0) para que el TAMAÑO de la respuesta
        # no revele a un observador de la red qué prefijo se consultó.
        pedido = urllib.request.Request(
            self.url_base + prefijo.upper(),
            headers={"User-Agent": USER_AGENT, "Add-Padding": "true"},
        )
        # La respuesta es texto plano (líneas "SUFIJO:CONTEO" separadas por CRLF).
        with urllib.request.urlopen(pedido, timeout=self.timeout) as resp:  # noqa: S310
            return resp.read().decode("utf-8")
