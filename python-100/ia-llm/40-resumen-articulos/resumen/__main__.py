"""Uso: python -m resumen <url | archivo.html>"""
import sys
from pathlib import Path

from resumen.extraccion import extraer
from resumen.llm import crear_proveedor
from resumen.obtencion import FetcherFalso, FetcherHTTP
from resumen.resumidor import a_markdown, resumir


def main(argv: list[str]) -> None:
    if not argv:
        print(__doc__); return
    origen = argv[0]
    # Si el argumento es un archivo local se lee sin red; si no, se trata como URL.
    fetcher = FetcherFalso({origen: origen}) if Path(origen).exists() else FetcherHTTP()
    art = extraer(fetcher.obtener(origen))
    prov = crear_proveedor()
    # Sin clave de LLM => resumen extractivo (llm=None).
    print(a_markdown(resumir(art, None if prov.nombre == "falso" else prov), art, origen))


if __name__ == "__main__":
    main(sys.argv[1:])
