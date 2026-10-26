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

# Identificación honesta: nombre del programa + contacto (nunca un navegador falso).
USER_AGENT_POR_DEFECTO = "py100-resenas/1.0 (proyecto educativo; +https://example.org/contacto)"


class ErrorHTTP(Exception):
    """Respuesta con estado 4xx/5xx; guarda el estado y la URL."""
    def __init__(self, estado: int, url: str) -> None:
        super().__init__(f"HTTP {estado} en {url}")
        self.estado, self.url = estado, url


class BloqueadoPorRobots(Exception):
    """La URL está prohibida por robots.txt para nuestro User-Agent."""


@dataclass(frozen=True)
class Respuesta:
    """Respuesta HTTP mínima, independiente del transporte."""
    estado: int
    cabeceras: dict[str, str]
    cuerpo: bytes
    url: str

    def texto(self) -> str:
        # Se respeta el charset declarado ("text/html; charset=latin-1"); por defecto UTF-8.
        tipo = self.cabeceras.get("content-type", "")
        cod = tipo.split("charset=")[-1].split(";")[0].strip() if "charset=" in tipo else "utf-8"
        # errors="replace": un byte inválido no rompe el scraping.
        return self.cuerpo.decode(cod, errors="replace")

    def json(self) -> Any:
        """Decodifica el cuerpo como JSON."""
        return json.loads(self.cuerpo)


# Interfaz del transporte: función (url, cabeceras) → Respuesta.
class Fetcher(Protocol):
    def __call__(self, url: str, cabeceras: dict[str, str]) -> Respuesta: ...


def fetcher_urllib(url: str, cabeceras: dict[str, str], timeout: float = 15.0) -> Respuesta:
    """Transporte real con la librería estándar (no lanza por 4xx/5xx)."""
    # Timeout para no quedar colgado ante un servidor que no responde.
    req = urllib.request.Request(url, headers=cabeceras)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (sólo http/https, validado antes)
            return Respuesta(r.status, {k.lower(): v for k, v in r.headers.items()}, r.read(), url)
    # urllib lanza excepción con 4xx/5xx; se convierte en Respuesta para decidir arriba qué hacer.
    except urllib.error.HTTPError as e:
        return Respuesta(e.code, {k.lower(): v for k, v in e.headers.items()}, e.read() or b"", url)


@dataclass
class ClienteEducado:
    """Cliente HTTP que respeta robots.txt, se identifica y limita el ritmo por host."""
    user_agent: str = USER_AGENT_POR_DEFECTO
    intervalo: float = 1.0                      # segundos mínimos entre pedidos al mismo host
    fetcher: Fetcher = fetcher_urllib
    respetar_robots: bool = True
    # Reloj y `dormir` inyectables: los tests verifican las esperas sin esperar de verdad.
    reloj: Callable[[], float] = time.monotonic
    dormir: Callable[[float], None] = time.sleep
    # Caché de robots.txt por host y momento del último pedido por host.
    _robots: dict[str, RobotFileParser] = field(default_factory=dict)
    _ultimo: dict[str, float] = field(default_factory=dict)

    def _host(self, url: str) -> str:
        """Devuelve "esquema://host[:puerto]"; rechaza file:, ftp:, etc."""
        p = urlsplit(url)
        # Caso borde: evita leer archivos locales (file:///etc/passwd) u otros esquemas.
        if p.scheme not in {"http", "https"} or not p.netloc:
            raise ValueError(f"URL no soportada: {url}")
        return f"{p.scheme}://{p.netloc}"

    def _esperar_turno(self, host: str) -> None:
        """Duerme lo necesario para respetar el intervalo (o el Crawl-delay) del host."""
        espera = self.intervalo
        rp = self._robots.get(host)
        # Se usa el mayor entre nuestro intervalo y el Crawl-delay que pide el sitio.
        if rp is not None and (cd := rp.crawl_delay(self.user_agent)):
            espera = max(espera, float(cd))
        if host in self._ultimo:
            # Sólo se espera lo que falta desde el último pedido (el primero no espera).
            faltan = espera - (self.reloj() - self._ultimo[host])
            if faltan > 0:
                self.dormir(faltan)
        self._ultimo[host] = self.reloj()

    def _pedir(self, url: str, host: str, extra: dict[str, str] | None) -> Respuesta:
        """Hace un pedido respetando el turno y con nuestro User-Agent."""
        self._esperar_turno(host)
        # Las cabeceras extra se agregan después y pueden completar las básicas.
        return self.fetcher(url, {"User-Agent": self.user_agent, **(extra or {})})

    def permitido(self, url: str) -> bool:
        """Consulta robots.txt (descargándolo una vez por host) para esa URL."""
        host = self._host(url)
        if not self.respetar_robots:
            return True
        if host not in self._robots:
            rp = RobotFileParser()
            # El propio robots.txt también respeta el ritmo y se pide con nuestro User-Agent.
            r = self._pedir(host + "/robots.txt", host, None)
            if r.estado in (401, 403):
                rp.disallow_all = True           # misma convención que robotparser
            elif r.estado >= 400:
                rp.allow_all = True              # sin robots.txt: todo permitido
            else:
                # 2xx: se interpretan las reglas del sitio.
                rp.parse(r.texto().splitlines())
            self._robots[host] = rp
        return self._robots[host].can_fetch(self.user_agent, url)

    def get(self, url: str, cabeceras: dict[str, str] | None = None) -> Respuesta:
        """GET con robots.txt y ritmo; lanza BloqueadoPorRobots o ErrorHTTP."""
        # Si robots.txt lo prohíbe, el pedido NUNCA llega a hacerse.
        if not self.permitido(url):
            raise BloqueadoPorRobots(url)
        r = self._pedir(url, self._host(url), cabeceras)
        if r.estado >= 400:
            raise ErrorHTTP(r.estado, url)
        return r
