"""autodoc: genera documentación Markdown/HTML leyendo docstrings vía AST."""
# API pública: modelo de datos, extractores y los dos renderizadores.
from .extractor import Clase, Funcion, Modulo, extraer_modulo, extraer_paquete
from .render import a_html, a_markdown

__all__ = ["Clase", "Funcion", "Modulo", "extraer_modulo", "extraer_paquete", "a_html", "a_markdown"]
