"""Descarga de páginas con buenas prácticas de scraping.

``HttpFetcher``:
- Consulta y respeta ``robots.txt`` (``urllib.robotparser``) antes de cada URL.
- Se identifica con un User-Agent honesto que incluye un contacto.
- Aplica un intervalo mínimo entre peticiones al mismo host (rate limiting);
  si robots.txt declara ``Crawl-delay`` se usa el mayor de ambos.

``FakeFetcher`` devuelve HTML desde un diccionario, para tests offline.
"""

from __future__ import annotations

import time
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Protocol
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

# User-Agent HONESTO: dice quiénes somos y cómo contactarnos. No se imita a un navegador para
# evadir protecciones; si un sitio bloquea este UA, la decisión correcta es no scrapearlo.
# ".invalid" es un TLD reservado (RFC 2606): hay que reemplazarlo por un contacto real.
UA_POR_DEFECTO = "ScraperCompetenciaBot/1.0 (+mailto:contacto@ejemplo.invalid)"


# Excepción propia para que el llamador distinga "no permitido" de un error de red.
class BloqueadoPorRobots(Exception):
    """Se lanza cuando robots.txt no permite acceder a la URL."""


class Fetcher(Protocol):
    """Contrato: dada una URL devuelve su HTML como texto."""

    def obtener(self, url: str) -> str: ...


@dataclass
class HttpFetcher:
    """Fetcher real basado en ``urllib`` (sin dependencias)."""

    user_agent: str = UA_POR_DEFECTO
    intervalo_min: float = 2.0
    timeout: float = 15.0
    # ``monotonic`` y no ``time.time``: no salta si cambia la hora del sistema (NTP, horario de verano).
    # Reloj y dormir son inyectables para testear el rate limiting sin esperar de verdad.
    reloj: Callable[[], float] = time.monotonic
    dormir: Callable[[float], None] = time.sleep
    # Cachés por host: robots.txt se descarga UNA vez por sitio y se recuerda la hora del último pedido.
    _robots: dict[str, RobotFileParser] = field(default_factory=dict)
    _ultimo: dict[str, float] = field(default_factory=dict)

    def _descargar(self, url: str) -> str:
        """GET simple con nuestro User-Agent; decodifica según el charset."""
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        # Timeout obligatorio: sin él, un servidor que no responde colgaría el proceso indefinidamente.
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
            # Se respeta el charset declarado por el servidor; errors="replace" evita abortar por un byte inválido.
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")

    def _robots_de(self, url: str) -> RobotFileParser:
        """Obtiene (y cachea por host) el robots.txt del sitio.

        Si robots.txt no existe (404) ``RobotFileParser`` permite todo, que es
        la semántica estándar del protocolo.
        """
        partes = urlsplit(url)
        # robots.txt siempre vive en la raíz del host (esquema + dominio + puerto).
        base = f"{partes.scheme}://{partes.netloc}"
        if base not in self._robots:
            rp = RobotFileParser()
            rp.set_url(base + "/robots.txt")
            try:
                rp.parse(self._descargar(base + "/robots.txt").splitlines())
            except urllib.error.HTTPError as e:
                # 401/403 => por convención se asume que no se permite nada.
                if e.code in (401, 403):
                    rp.disallow_all = True
                # Otros errores HTTP (típicamente 404): no hay robots.txt → se permite todo (semántica estándar).
                else:
                    rp.allow_all = True
            self._robots[base] = rp
        return self._robots[base]

    def permitido(self, url: str) -> bool:
        """``True`` si robots.txt permite a nuestro UA acceder a ``url``."""
        return self._robots_de(url).can_fetch(self.user_agent, url)

    def _esperar_turno(self, url: str) -> None:
        """Rate limiting por host: duerme lo necesario desde la última petición."""
        host = urlsplit(url).netloc
        # Se usa la demora más conservadora entre la nuestra y el Crawl-delay que pida el sitio.
        demora = max(self.intervalo_min, float(self._robots_de(url).crawl_delay(self.user_agent) or 0))
        ahora = self.reloj()
        # Primera petición a un host: no se espera. Siguientes: se duerme sólo lo que falte
        # para completar ``demora`` desde la última (si ya pasó más tiempo, no se duerme).
        if host in self._ultimo:
            restante = self._ultimo[host] + demora - ahora
            if restante > 0:
                self.dormir(restante)
        # Se vuelve a leer el reloj DESPUÉS de dormir: la próxima espera se mide desde el pedido real.
        self._ultimo[host] = self.reloj()

    def obtener(self, url: str) -> str:
        # Orden: primero robots.txt (si no está permitido no se hace ni el pedido), luego el turno, luego el GET.
        if not self.permitido(url):
            raise BloqueadoPorRobots(url)
        self._esperar_turno(url)
        return self._descargar(url)


@dataclass
class FakeFetcher:
    """Fetcher en memoria: ``paginas`` mapea URL -> HTML."""

    paginas: dict[str, str]
    pedidas: list[str] = field(default_factory=list)

    def obtener(self, url: str) -> str:
        # Registro de URLs pedidas: permite verificar en tests el orden de la paginación.
        self.pedidas.append(url)
        return self.paginas[url]
