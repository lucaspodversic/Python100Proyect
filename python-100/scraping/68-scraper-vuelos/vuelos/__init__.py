"""vuelos: parser genérico de resultados de vuelos + comparación y alertas de precio.

No apunta a ninguna aerolínea ni buscador por defecto: ver README (términos de uso
y APIs oficiales como Amadeus Self-Service o las APIs NDC de las aerolíneas).
"""
# API pública: modelo/normalización, parsers guiados por perfil y comparación.
from .modelo import Vuelo, parsear_duracion, parsear_precio
from .parser import PerfilVuelos, parsear_html, parsear_json
from .comparar import Criterio, ordenar, filtrar, resumen_por_aerolinea, HistorialPrecios

__all__ = ["Vuelo", "parsear_duracion", "parsear_precio", "PerfilVuelos", "parsear_html", "parsear_json",
           "Criterio", "ordenar", "filtrar", "resumen_por_aerolinea", "HistorialPrecios"]
