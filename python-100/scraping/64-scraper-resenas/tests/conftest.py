"""Servidor HTTP local (127.0.0.1, puerto efímero) que sirve fixtures.

Se usa como fixture de pytest: nunca se contacta Internet.
"""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Iterator

import pytest


def crear_servidor(rutas: dict[str, tuple[int, str, bytes]]):
    """rutas: path → (estado, content-type, cuerpo). Registra los pedidos."""
    # Registro (ruta, User-Agent) de cada pedido: los tests verifican qué se pidió y cómo.
    pedidos: list[tuple[str, str]] = []

    class Manejador(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (nombre impuesto por http.server)
            pedidos.append((self.path, self.headers.get("User-Agent", "")))
            # Rutas no definidas → 404 (así se simula un sitio sin robots.txt).
            estado, tipo, cuerpo = rutas.get(self.path, (404, "text/plain", b"no encontrado"))
            self.send_response(estado)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def log_message(self, *args) -> None:  # silencio en los tests
            pass

    # Puerto 0 = el sistema elige uno libre; sólo escucha en localhost.
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
    # Hilo daemon: no impide que termine pytest; poll_interval corto para apagar rápido.
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    return srv, pedidos


@pytest.fixture
def servidor() -> Iterator:
    """Devuelve una función que levanta el servidor con las rutas dadas."""
    creados = []

    def _levantar(rutas):
        srv, pedidos = crear_servidor(rutas)
        creados.append(srv)
        return f"http://127.0.0.1:{srv.server_address[1]}", pedidos

    # Al terminar el test se apagan y cierran todos los servidores creados.
    yield _levantar
    for s in creados:
        s.shutdown()
        s.server_close()
