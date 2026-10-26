# 03 · Web scraper de competencia

Extrae **precios y características** de productos de catálogos web y los exporta a una **planilla (Excel/CSV)**, comparando contra tus propios precios.

## Qué demuestra
- Scraping con BeautifulSoup y selectores CSS configurables por sitio (sin tocar código para sumar competidores).
- Parseo robusto de precios en formatos regionales (`$ 1.234,56`, `US$1,234.56`).
- Paginación con cota anti-bucles.
- Exportación a Excel con formato (openpyxl) y diferencia % vs precio propio.
- **Scraping ético** incorporado en el código:
  - consulta y respeta `robots.txt` (incluido `Crawl-delay`);
  - User-Agent **honesto** con contacto (no se hace pasar por un navegador);
  - rate limiting por host.

## Arquitectura
```
src/scraper_competencia/
├── modelos.py   # ReglasSitio (selectores), Producto
├── fetcher.py   # Fetcher (Protocol), HttpFetcher (robots + UA + rate limit), FakeFetcher
├── parser.py    # parsear_precio, extraer_productos, recorrer (paginación)
├── exportar.py  # exportar_csv, exportar_xlsx
└── cli.py       # configuración JSON -> planilla
tests/fixtures/sitio/  # sitio de prueba (HTML + robots.txt) servido en 127.0.0.1
```

## Instalación
```bash
pip install -e ".[dev]"     # o: pip install -r requirements.txt -r requirements-dev.txt
```

## Uso
`config.json`:
```json
{"sitios": [{"url": "https://tienda-autorizada.example/catalogo",
             "reglas": {"nombre": "Competidor A", "tarjeta": "div.producto", "titulo": ".titulo",
                        "precio": ".precio", "sku": ".sku", "enlace": "a", "siguiente": "a.siguiente",
                        "extras": {"marca": ".marca"}}}],
 "propios": {"A1": "12000"}}
```
```bash
scraper-competencia config.json -o competencia.xlsx --intervalo 3
```

> ⚠️ Usalo sólo con sitios cuyos términos de uso lo permitan (o con APIs/feeds oficiales cuando existan). El proyecto no incluye URLs reales de terceros.

## Tests
```bash
pytest
```
Usan fixtures HTML locales y un servidor `http.server` en `127.0.0.1` (puerto efímero). No acceden a Internet.

## Limitaciones
- No ejecuta JavaScript: sitios que renderizan el catálogo en el cliente requieren su API pública o un navegador headless.
- La heurística de precios asume que 1–2 dígitos tras el último separador son decimales.
