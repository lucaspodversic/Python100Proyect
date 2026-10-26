"""Cliente HTTP "educado" para scraping responsable.

Reglas que aplica SIEMPRE:
1. **robots.txt**: antes de pedir una URL se descarga (una vez por host)
   y se consulta con `urllib.robotparser`. Si prohíbe la ruta, se lanza
   `BloqueadoPorRobots` y NO se hace el pedido.
2. **User-Agent honesto**: identifica al programa y un contacto; nunca
   se hace pasar por un navegador.
3. **Rate limiting** por host: espera mínima entre pedidos (o el
   `Crawl-delay` de robots.txt si es mayor).

El transporte (`Fetcher`) es inyectable: en los tests se usa un servidor
local en 127.0.0.1 o un fake en memoria, sin tocar Internet.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

# Identificación pública del programa: nombre/versión + URL de contacto,
# como recomiendan las buenas prácticas (el admin del sitio sabe quién pide).
USER_AGENT_POR_DEFECTO = "py100-monitor_web/1.0 (proyecto educativo; +https://example.org/contacto)"


class ErrorHTTP(Exception):
    """Respuesta con estado >= 400 (el transporte no lanza; lo decide el cliente)."""

    def __init__(self, estado: int, url: str) -> None:
        super().__init__(f"HTTP {estado} en {url}")
        # Se guardan por separado para que quien capture pueda decidir según el código.
        self.estado, self.url = estado, url


class BloqueadoPorRobots(Exception):
    """La URL está prohibida por robots.txt para nuestro User-Agent."""


@dataclass(frozen=True)
class Respuesta:
    """Respuesta HTTP ya leída en memoria (inmutable, fácil de construir en tests)."""

    estado: int                 # código HTTP (200, 304, 404…)
    cabeceras: dict[str, str]   # nombres en minúscula para buscar sin importar mayúsculas
    cuerpo: bytes               # bytes crudos: el decodificado se hace bajo demanda
    url: str                    # URL pedida (útil para mensajes y para resolver enlaces relativos)

    def texto(self) -> str:
        """Decodifica el cuerpo con el charset de Content-Type (UTF-8 si no viene)."""
        tipo = self.cabeceras.get("content-type", "")
        # "text/html; charset=ISO-8859-1" → "ISO-8859-1"; se corta en ';' por si hay más parámetros.
        cod = tipo.split("charset=")[-1].split(";")[0].strip() if "charset=" in tipo else "utf-8"
        # errors="replace": un byte inválido no debe tumbar el scraping entero.
        return self.cuerpo.decode(cod, errors="replace")

    def json(self) -> Any:
        """Interpreta el cuerpo como JSON (json.loads acepta bytes UTF-8/16/32)."""
        return json.loads(self.cuerpo)


class Fetcher(Protocol):
    """Contrato del transporte: recibe URL y cabeceras, devuelve una Respuesta (sin lanzar por 4xx/5xx)."""

    def __call__(self, url: str, cabeceras: dict[str, str]) -> Respuesta: ...


def fetcher_urllib(url: str, cabeceras: dict[str, str], timeout: float = 15.0) -> Respuesta:
    """Transporte real con la librería estándar (no lanza por 4xx/5xx)."""
    req = urllib.request.Request(url, headers=cabeceras)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (sólo http/https, validado antes)
            return Respuesta(r.status, {k.lower(): v for k, v in r.headers.items()}, r.read(), url)
    except urllib.error.HTTPError as e:
        # urllib convierte 4xx/5xx en excepción; la transformamos de nuevo en Respuesta
        # para que el cliente trate todos los estados de forma uniforme.
        return Respuesta(e.code, {k.lower(): v for k, v in e.headers.items()}, e.read() or b"", url)


@dataclass
class ClienteEducado:
    """Cliente con robots.txt, User-Agent honesto y pausa por host. Todo inyectable para tests."""

    user_agent: str = USER_AGENT_POR_DEFECTO
    intervalo: float = 1.0                      # segundos mínimos entre pedidos al mismo host
    fetcher: Fetcher = fetcher_urllib           # transporte (real o falso)
    respetar_robots: bool = True                # sólo se desactiva para APIs oficiales (documentado en el README)
    reloj: Callable[[], float] = time.monotonic  # monotónico: no salta con cambios de hora del sistema
    dormir: Callable[[float], None] = time.sleep  # en tests se reemplaza para no esperar de verdad
    _robots: dict[str, RobotFileParser] = field(default_factory=dict)  # caché de robots.txt por host
    _ultimo: dict[str, float] = field(default_factory=dict)            # momento del último pedido por host

    def _host(self, url: str) -> str:
        """'https://a.com/x?y' → 'https://a.com'. Rechaza file://, ftp://, etc. (evita leer archivos locales)."""
        p = urlsplit(url)
        if p.scheme not in {"http", "https"} or not p.netloc:
            raise ValueError(f"URL no soportada: {url}")
        return f"{p.scheme}://{p.netloc}"

    def _esperar_turno(self, host: str) -> None:
        """Duerme lo necesario para respetar el intervalo (o el Crawl-delay, si es mayor)."""
        espera = self.intervalo
        rp = self._robots.get(host)
        # El := evita llamar dos veces a crawl_delay; None o 0 significa "sin indicación".
        if rp is not None and (cd := rp.crawl_delay(self.user_agent)):
            espera = max(espera, float(cd))
        if host in self._ultimo:
            # Sólo se duerme el tiempo que falta desde el último pedido, no el intervalo completo.
            faltan = espera - (self.reloj() - self._ultimo[host])
            if faltan > 0:
                self.dormir(faltan)
        self._ultimo[host] = self.reloj()

    def _pedir(self, url: str, host: str, extra: dict[str, str] | None) -> Respuesta:
        """Pedido crudo: respeta el turno y agrega siempre el User-Agent (las cabeceras extra no lo pisan… salvo a propósito)."""
        self._esperar_turno(host)
        return self.fetcher(url, {"User-Agent": self.user_agent, **(extra or {})})

    def permitido(self, url: str) -> bool:
        """¿robots.txt permite esta URL a nuestro User-Agent? Descarga robots.txt una sola vez por host."""
        host = self._host(url)
        if not self.respetar_robots:
            return True
        if host not in self._robots:
            rp = RobotFileParser()
            r = self._pedir(host + "/robots.txt", host, None)
            if r.estado in (401, 403):
                rp.disallow_all = True           # misma convención que robotparser: acceso denegado = no rastrear
            elif r.estado >= 400:
                rp.allow_all = True              # sin robots.txt (404, 5xx): todo permitido
            else:
                rp.parse(r.texto().splitlines())
            self._robots[host] = rp
        return self._robots[host].can_fetch(self.user_agent, url)

    def get(self, url: str, cabeceras: dict[str, str] | None = None) -> Respuesta:
        """GET educado: primero robots.txt, luego el pedido; lanza ErrorHTTP si el estado es >= 400."""
        if not self.permitido(url):
            raise BloqueadoPorRobots(url)     # se lanza ANTES de pedir: lo prohibido nunca se descarga
        r = self._pedir(url, self._host(url), cabeceras)
        if r.estado >= 400:
            raise ErrorHTTP(r.estado, url)
        return r      # 2xx y 3xx (p. ej. 304 Not Modified) se devuelven tal cual
