"""wikiextractor: datos de artículos de Wikipedia usando la API de MediaWiki."""
# API pública: cliente de MediaWiki y extractores de resumen, secciones, infobox y tablas.
from .api import ApiWikipedia
from .extraer import Articulo, extraer_articulo, tablas, infobox, resumen, secciones

__all__ = ["ApiWikipedia", "Articulo", "extraer_articulo", "tablas", "infobox", "resumen", "secciones"]
