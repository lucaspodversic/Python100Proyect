"""resenas: extrae reseñas con un parser genérico y analiza su sentimiento.

No apunta a Amazon ni a ningún sitio por defecto (sus términos prohíben el scraping).
"""
# API pública: modelo, parsers (HTML con perfil CSS y JSON-LD), sentimiento y resumen.
from .modelo import Resena
from .parser import PerfilResenas, parsear_html, parsear_jsonld
from .sentimiento import puntuar, clasificar
from .resumen import Resumen, resumir

__all__ = ["Resena", "PerfilResenas", "parsear_html", "parsear_jsonld", "puntuar", "clasificar",
           "Resumen", "resumir"]
