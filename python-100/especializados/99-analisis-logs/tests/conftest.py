"""Rutas a los logs de ejemplo (fixtures versionadas en tests/fixtures).

apache_access.log (17 líneas): 16 válidas + 1 basura. Contiene un usuario en
escritorio con dos visitas (pausa de 55 min), uno en iPhone con un 500, un
Googlebot, un escáner que dispara 5 errores 4xx y un cliente en zona +0200.

nginx_access.log (7 líneas): formato combined + $request_time al final
(campo extra que debe ignorarse), una IPv6 y un handshake TLS enviado al
puerto HTTP (línea inválida típica).
"""
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture()
def apache() -> Path:
    """Log de ejemplo en formato Apache combinado (16 líneas válidas y 1 inválida a propósito)."""
    return FIX / "apache_access.log"


@pytest.fixture()
def nginx() -> Path:
    """Log de ejemplo en formato Nginx."""
    return FIX / "nginx_access.log"
