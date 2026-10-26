"""Acceso a la API oficial de MediaWiki (`/w/api.php`).

Se usa la API y no el HTML público porque así lo recomienda Wikimedia.
Cumplimos su *API Etiquette* y su política de User-Agent:
- User-Agent descriptivo con contacto (configurable con --contacto).
- Pedidos en serie, con pausa mínima entre ellos.
- Parámetro `maxlag=5`: si los servidores están cargados, la API
  responde error y nosotros esperamos.

Nota sobre robots.txt: ese archivo regula a los *crawlers* de páginas
y Wikimedia excluye `/w/` para ellos; el uso programático de la API
se rige por la API Etiquette (arriba). Por eso este cliente desactiva
explícitamente la consulta a robots.txt sólo para el endpoint de API.
"""
from __future__ import annotations

from urllib.parse import urlencode

from .cliente import ClienteEducado, ErrorHTTP


class ErrorWiki(Exception):
    """La API respondió con un objeto "error" (título inexistente, maxlag, etc.)."""
    pass


class ApiWikipedia:
    """Cliente mínimo de /w/api.php para buscar títulos y obtener el HTML de un artículo."""
    def __init__(self, idioma: str = "es", cliente: ClienteEducado | None = None,
                 url_api: str | None = None, contacto: str = "https://example.org/contacto") -> None:
        # El idioma va dentro del nombre de host: se valida para no armar URLs a otros dominios.
        if not idioma.isalpha() or len(idioma) > 12:
            raise ValueError("Código de idioma inválido")
        self.url_api = url_api or f"https://{idioma}.wikipedia.org/w/api.php"
        # 1 s entre pedidos, en serie; robots.txt desactivado sólo aquí (ver docstring del módulo).
        self.cliente = cliente or ClienteEducado(
            user_agent=f"py100-wikiextractor/1.0 ({contacto})", intervalo=1.0, respetar_robots=False)

    def _llamar(self, **params: str) -> dict:
        """Hace un pedido a la API con los parámetros comunes y convierte errores en ErrorWiki."""
        # formatversion=2 da un JSON más simple; maxlag=5 cede ante servidores cargados.
        params |= {"format": "json", "formatversion": "2", "maxlag": "5"}
        datos = self.cliente.get(f"{self.url_api}?{urlencode(params)}").json()
        # MediaWiki devuelve HTTP 200 incluso con errores: hay que mirar el cuerpo.
        if "error" in datos:
            raise ErrorWiki(f"{datos['error'].get('code')}: {datos['error'].get('info')}")
        return datos

    def buscar(self, termino: str, limite: int = 5) -> list[str]:
        """Títulos que coinciden con `termino` (list=search), como máximo `limite`."""
        d = self._llamar(action="query", list="search", srsearch=termino, srlimit=str(limite))
        return [r["title"] for r in d["query"]["search"]]

    def html_articulo(self, titulo: str) -> tuple[str, str]:
        """Devuelve (título normalizado, HTML renderizado del artículo)."""
        # redirects=1 sigue redirecciones; sin enlaces de edición ni índice para un HTML más limpio.
        d = self._llamar(action="parse", page=titulo, prop="text", redirects="1",
                         disableeditsection="1", disabletoc="1")
        return d["parse"]["title"], d["parse"]["text"]


# ErrorHTTP se re-exporta para que la CLI importe todo desde aquí.
__all__ = ["ApiWikipedia", "ErrorWiki", "ErrorHTTP"]
