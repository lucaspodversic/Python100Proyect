# 63 · Extractor de datos de Wikipedia

Obtiene el resumen, las secciones, la infobox y las tablas de un artículo de Wikipedia
y exporta las tablas a CSV.

## Qué demuestra
- Uso de la **API oficial de MediaWiki** (`action=parse`, `list=search`) en lugar de scrapear HTML.
- Cumplimiento de la *API Etiquette* de Wikimedia: User-Agent descriptivo con contacto,
  pedidos en serie con pausa, `maxlag=5`.
- BeautifulSoup: limpieza de referencias `[1]`, infobox → dict y `table.wikitable` → grilla,
  **expandiendo `colspan`/`rowspan`**.

## Sobre robots.txt
`robots.txt` de Wikipedia está dirigido a *crawlers* de páginas y excluye `/w/`; el acceso
programático a la API está regulado por la **API Etiquette**, que este proyecto cumple. Por eso
el cliente de API desactiva explícitamente la consulta a robots.txt sólo para ese endpoint
(el `ClienteEducado` incluido la aplica por defecto para cualquier otro uso).

## Arquitectura
```
wikiextractor/
  cliente.py  # ClienteEducado (UA honesto, ritmo, robots.txt)
  api.py      # ApiWikipedia: buscar, html_articulo
  extraer.py  # resumen, secciones, infobox, tablas, Articulo
  cli.py
```

## Instalación y uso
```bash
pip install -e ".[dev]"
python -m wikiextractor "Python (lenguaje de programación)" --contacto tu@email.com
python -m wikiextractor "Anexo:Países por población" --tablas tablas/
python -m wikiextractor "Buenos Aires" --idioma es --json > ba.json
python -m wikiextractor "python" --buscar
```

## Tests
```bash
pytest
```
Respuestas de la API guardadas como fixtures y servidas desde `127.0.0.1`.

## Limitaciones
- Las infobox varían mucho entre artículos/idiomas; se extraen pares `th`/`td` genéricos.
- Para volcados masivos usá los *dumps* oficiales (dumps.wikimedia.org), no la API.
