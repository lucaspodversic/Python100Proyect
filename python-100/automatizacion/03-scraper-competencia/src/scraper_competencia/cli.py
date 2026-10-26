"""CLI: lee un JSON de configuración con sitios y selectores y exporta resultados.

Formato de configuración::

    {"sitios": [{"url": "https://...", "reglas": {"nombre": "...", "tarjeta": "...", ...}}],
     "propios": {"SKU1": "1000.00"}}

Sólo scrapeá sitios cuyos términos lo permitan; el fetcher respeta robots.txt.
"""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

from .exportar import exportar_csv, exportar_xlsx
from .fetcher import Fetcher, HttpFetcher
from .modelos import ReglasSitio
from .parser import recorrer


def ejecutar(config: dict, fetcher: Fetcher, salida: Path) -> int:
    """Corre el scraping descrito por ``config`` y exporta según la extensión."""
    # Se acumulan los productos de todos los competidores en una única tabla de salida.
    productos = []
    for sitio in config["sitios"]:
        # ``ReglasSitio(**...)``: el JSON trae los selectores CSS; una clave desconocida produce
        # TypeError inmediato (preferible a ignorar silenciosamente un error de tipeo).
        productos += recorrer(fetcher, sitio["url"], ReglasSitio(**sitio["reglas"]))
    # Precios propios como Decimal desde texto ("1000.00") para evitar errores de coma flotante.
    # ``or None``: un dict vacío equivale a "no comparar" y no agrega columnas.
    propios = {k: Decimal(v) for k, v in config.get("propios", {}).items()} or None
    # El formato se elige por la extensión del archivo de salida; cualquier otra cosa → CSV.
    (exportar_xlsx if salida.suffix == ".xlsx" else exportar_csv)(productos, salida, propios)
    return len(productos)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="scraper-competencia", description=__doc__)
    p.add_argument("config", type=Path)
    p.add_argument("-o", "--salida", type=Path, default=Path("competencia.xlsx"))
    # 2 s por defecto entre peticiones al mismo host: conservador, para no cargar el sitio ajeno.
    p.add_argument("--intervalo", type=float, default=2.0, help="segundos mínimos entre peticiones")
    a = p.parse_args(argv)
    n = ejecutar(json.loads(a.config.read_text(encoding="utf-8")), HttpFetcher(intervalo_min=a.intervalo), a.salida)
    print(f"{n} productos exportados a {a.salida}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
