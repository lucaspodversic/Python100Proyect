"""Scraper de precios de la competencia (ético: robots.txt + UA honesto + rate limit)."""

# Capas del paquete: fetcher (red, robots.txt, rate limit) → parser (HTML → Producto)
# → exportar (CSV/XLSX). Cada capa se puede testear y reemplazar por separado.
from .fetcher import BloqueadoPorRobots, Fetcher, FakeFetcher, HttpFetcher
from .modelos import Producto, ReglasSitio
from .parser import extraer_productos, parsear_precio
from .exportar import exportar_csv, exportar_xlsx

__all__ = [
    "Fetcher", "HttpFetcher", "FakeFetcher", "BloqueadoPorRobots",
    "Producto", "ReglasSitio", "extraer_productos", "parsear_precio",
    "exportar_csv", "exportar_xlsx",
]
