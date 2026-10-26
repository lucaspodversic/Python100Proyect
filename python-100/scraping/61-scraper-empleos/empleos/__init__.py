"""empleos: extrae ofertas de empleo de páginas HTML con un parser genérico.

No apunta a ningún sitio por defecto. LinkedIn e InfoJobs prohíben el
scraping en sus términos: para ellos usá sus APIs/feeds oficiales.
"""
# API pública: modelo, parsers y pipeline (el cliente HTTP se importa aparte desde empleos.cliente).
from .modelo import Oferta, parsear_salario
from .parser import PerfilSelectores, parsear_html, parsear_jsonld
from .pipeline import Filtro, ejecutar_pipeline, exportar

__all__ = ["Oferta", "parsear_salario", "PerfilSelectores", "parsear_html", "parsear_jsonld",
           "Filtro", "ejecutar_pipeline", "exportar"]
