"""Obtención del HTML detrás de una interfaz (`Fetcher`).

`FetcherHTTP` aplica precauciones básicas: solo http/https, tamaño máximo,
verificación de Content-Type y timeout. `FetcherFalso` devuelve fixtures
locales para tests (sin red).
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

import httpx


class ErrorObtencion(RuntimeError):
    pass


class Fetcher(Protocol):
    def obtener(self, url: str) -> str: ...


class FetcherHTTP:
    def __init__(self, cliente: httpx.Client | None = None, max_bytes: int = 3_000_000) -> None:
        self._cliente = cliente or httpx.Client(timeout=20, follow_redirects=True,
                                                headers={"User-Agent": "resumidor-articulos/1.0"})
        self.max_bytes = max_bytes

    def obtener(self, url: str) -> str:
        # Bloquea file://, ftp://, etc. (evita leer archivos locales vía URL).
        if urlparse(url).scheme not in ("http", "https"):
            raise ErrorObtencion("Solo se permiten URLs http/https")
        try:
            # stream: se revisan cabeceras y tamaño ANTES de bajar todo el cuerpo.
            with self._cliente.stream("GET", url) as r:
                r.raise_for_status()
                if "html" not in r.headers.get("content-type", ""):
                    raise ErrorObtencion(f"No es HTML: {r.headers.get('content-type')}")
                datos = b""
                for trozo in r.iter_bytes():
                    datos += trozo
                    if len(datos) > self.max_bytes:   # corta descargas gigantes
                        raise ErrorObtencion("Página demasiado grande")
                # errors="replace": un byte inválido no rompe todo el resumen.
                return datos.decode(r.encoding or "utf-8", errors="replace")
        # Se unifican los errores de red/HTTP en ErrorObtencion (un solo tipo).
        except httpx.HTTPError as e:
            raise ErrorObtencion(str(e)) from e


class FetcherFalso:
    """Mapea URL -> archivo HTML local."""

    def __init__(self, paginas: dict[str, str | Path]) -> None:
        self.paginas = paginas

    def obtener(self, url: str) -> str:
        if url not in self.paginas:
            raise ErrorObtencion(f"404: {url}")
        return Path(self.paginas[url]).read_text(encoding="utf-8")
