"""Cliente de la búsqueda de repositorios de GitHub (GET /search/repositories).

GitHub no expone "trending" como API; se aproxima con:
    q = created:>=FECHA [language:X] [topic:Y] [stars:>=N]   sort=stars order=desc

Decisión documentada: api.github.com publica un robots.txt que excluye a los
*crawlers*; el uso de la API REST se rige por sus términos y límites
(60 pedidos/h sin token, 5000/h con token; búsqueda: 10/min sin token, 30/min con token).
Por eso `respetar_robots=False` sólo para este host de API, con pausa entre pedidos,
User-Agent identificable (obligatorio para GitHub) y manejo de rate limit.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode

from .cliente import ClienteEducado, ErrorHTTP

API = "https://api.github.com"


class LimiteExcedido(RuntimeError):
    """Se agotó el cupo de la API. `reinicio` indica cuándo vuelve a haber cupo (si GitHub lo informó)."""

    def __init__(self, reinicio: datetime | None) -> None:
        cuando = f" (se reinicia {reinicio:%H:%M} UTC)" if reinicio else ""
        # Mensaje accionable: qué pasó y las dos salidas posibles (token o esperar).
        super().__init__(f"Límite de la API de GitHub excedido{cuando}. Usá GITHUB_TOKEN o esperá.")
        self.reinicio = reinicio


@dataclass(frozen=True)
class Repo:
    """Datos de un repositorio que se usan en el ranking."""

    nombre: str          # "dueño/repo"
    url: str
    descripcion: str     # "" si el repo no tiene descripción
    lenguaje: str        # "—" si GitHub no detectó lenguaje
    estrellas: int
    forks: int
    creado: datetime     # aware, en UTC
    temas: tuple[str, ...]

    def estrellas_por_dia(self, ahora: datetime) -> float:
        """Ritmo de crecimiento: estrellas / días de vida, con 1 decimal."""
        dias = max((ahora - self.creado).total_seconds() / 86400, 1.0)   # mínimo 1 día evita inflar recién creados
        return round(self.estrellas / dias, 1)


def construir_consulta(desde: date, lenguaje: str | None = None, tema: str | None = None,
                       min_estrellas: int | None = None) -> str:
    """Arma el parámetro `q` con la sintaxis de búsqueda de GitHub (calificadores separados por espacio)."""
    partes = [f"created:>={desde.isoformat()}"]
    if lenguaje:
        # Lenguajes con espacio ("Jupyter Notebook") van entre comillas; si no, GitHub los partiría.
        partes.append(f'language:"{lenguaje}"' if " " in lenguaje else f"language:{lenguaje}")
    if tema:
        partes.append(f"topic:{tema}")
    # 0 o None = sin mínimo (no se agrega el calificador).
    if min_estrellas:
        partes.append(f"stars:>={min_estrellas}")
    return " ".join(partes)


class ApiGitHub:
    """Búsqueda paginada con cabeceras oficiales, token opcional y detección de rate limit."""

    def __init__(self, cliente: ClienteEducado | None = None, token: str | None = None, base: str = API) -> None:
        # 2 s entre pedidos: sin token la búsqueda admite 10/min, así nunca se llega al límite.
        self.cliente = cliente or ClienteEducado(intervalo=2.0, respetar_robots=False)
        # rstrip("/"): "http://x/" y "http://x" producen la misma URL final.
        self.token, self.base = token, base.rstrip("/")

    def _cabeceras(self) -> dict[str, str]:
        """Cabeceras recomendadas por GitHub; Authorization sólo si hay token."""
        # Fijar la versión de la API evita cambios inesperados cuando GitHub publique una nueva.
        c = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            c["Authorization"] = f"Bearer {self.token}"
        return c

    def buscar(self, consulta: str, cantidad: int = 25, por_pagina: int = 100) -> list[Repo]:
        """Pagina de a 100 (máximo de GitHub) hasta juntar `cantidad` (la búsqueda tope es 1000)."""
        # GitHub sólo devuelve los primeros 1000 resultados de una búsqueda: pedir más no tiene sentido.
        if not 1 <= cantidad <= 1000:
            raise ValueError("cantidad debe estar entre 1 y 1000")
        repos: list[Repo] = []
        # Tamaño de página: nunca más de 100 (límite de GitHub) ni más de lo pedido (ahorra datos).
        pagina, por_pagina = 1, min(por_pagina, 100, cantidad)
        while len(repos) < cantidad:
            params = {"q": consulta, "sort": "stars", "order": "desc", "per_page": por_pagina, "page": pagina}
            try:
                d = self.cliente.get(f"{self.base}/search/repositories?{urlencode(params)}", self._cabeceras()).json()
            except ErrorHTTP as exc:
                r = exc.respuesta
                # GitHub señala el rate limit con 403 o 429 y además
                # x-ratelimit-remaining: 0 (límite primario) o retry-after (límite secundario).
                # Un 403 sin esas cabeceras es otro error (permisos) y se re-lanza tal cual.
                if exc.estado in (403, 429) and r is not None and (r.cabeceras.get("x-ratelimit-remaining") == "0"
                                                                    or "retry-after" in r.cabeceras):
                    # x-ratelimit-reset es un timestamp Unix en segundos (UTC).
                    reset = r.cabeceras.get("x-ratelimit-reset")
                    raise LimiteExcedido(datetime.fromtimestamp(int(reset), timezone.utc) if reset else None) from exc
                raise
            items = d.get("items", [])
            repos.extend(_repo(i) for i in items)
            # Página incompleta = era la última; evita un pedido extra que vendría vacío.
            if len(items) < por_pagina:
                break               # no hay más resultados
            pagina += 1
        # La última página puede traer más de lo necesario: se recorta.
        return repos[:cantidad]

    def tendencias(self, dias: int = 7, hoy: date | None = None, **filtros) -> list[Repo]:
        """Repos creados en los últimos `dias` días, por estrellas. `filtros` = lenguaje, tema, min_estrellas, cantidad."""
        # `hoy` inyectable para tests deterministas; por defecto la fecha UTC (la que usa GitHub).
        hoy = hoy or datetime.now(timezone.utc).date()
        # `cantidad` va a buscar(); el resto de filtros, a construir_consulta().
        cantidad = filtros.pop("cantidad", 25)
        return self.buscar(construir_consulta(hoy - timedelta(days=dias), **filtros), cantidad)


def _repo(i: dict) -> Repo:
    """JSON de un item de búsqueda → Repo, tolerando campos null o ausentes."""
    # description/language pueden venir null; "Z" se reemplaza para fromisoformat en Python < 3.11.
    return Repo(i["full_name"], i["html_url"], i.get("description") or "", i.get("language") or "—",
                int(i.get("stargazers_count", 0)), int(i.get("forks_count", 0)),
                datetime.fromisoformat(i["created_at"].replace("Z", "+00:00")), tuple(i.get("topics", [])))
