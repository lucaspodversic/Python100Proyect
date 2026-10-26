"""Fixtures compartidas: servidor HTTP local (127.0.0.1) con las páginas de prueba."""

from __future__ import annotations

import functools
import http.server
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

SITIO = Path(__file__).parent / "fixtures" / "sitio"


class _Silencioso(http.server.SimpleHTTPRequestHandler):
    """Handler que no ensucia la salida de pytest con logs de acceso."""

    def log_message(self, *args: object) -> None:  # noqa: D401
        pass


@pytest.fixture(scope="session")
def servidor_local() -> Iterator[str]:
    """Levanta un servidor en un puerto libre de 127.0.0.1 y devuelve su URL base."""
    # ``directory`` sirve los fixtures (catálogos HTML + robots.txt) sin cambiar el cwd del proceso.
    handler = functools.partial(_Silencioso, directory=str(SITIO))
    # Puerto 0 = el SO asigna uno libre (evita choques en CI). Sólo 127.0.0.1: nunca se sale a la red.
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    # Hilo daemon: si algo falla, no impide que pytest termine.
    hilo = threading.Thread(target=srv.serve_forever, daemon=True)
    hilo.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    # Teardown de la fixture de sesión: se ejecuta una vez al terminar todos los tests.
    srv.shutdown()
