# 61 · Scraper de ofertas de empleo (genérico)

Extrae ofertas de páginas de listados, las normaliza (salario, moneda, remoto),
las filtra, deduplica y exporta a CSV/JSON.

> ⚠️ **Limitación importante / términos de uso**: LinkedIn e InfoJobs **prohíben el
> scraping** en sus condiciones y bloquean activamente los bots. Este proyecto **no apunta a
> ningún sitio por defecto** ni trae selectores para ellos. Alternativas oficiales:
> - **InfoJobs**: API para desarrolladores (`developer.infojobs.net`) con credenciales propias.
> - **LinkedIn**: Job Posting / Talent APIs para socios, o alertas de empleo por correo.
> - Muchos portales y empresas publican **feeds RSS/XML** o datos `JobPosting` de schema.org.
>
> Usá el scraper sólo con sitios cuyos términos lo permitan.

## Qué demuestra
- Parser **genérico** en dos niveles: datos estructurados **JSON-LD `JobPosting`** (robusto)
  y **selectores CSS configurables** en JSON (`PerfilSelectores`) con paginación.
- Normalización de salarios en texto libre (`40.000 - 55.000 €`, `US$ 3k`, `2,5 mil usd`).
- Cliente **educado**: respeta `robots.txt` (incluido `Crawl-delay`), User-Agent honesto
  `py100-empleos/1.0`, límite de ritmo por host. Si robots prohíbe, no se hace el pedido (código 3).
- Pipeline testeable: descargar → parsear → filtrar → deduplicar → exportar.

## Arquitectura
```
empleos/
  cliente.py   # ClienteEducado (robots.txt, UA, rate limit), transporte inyectable
  modelo.py    # Oferta, parsear_salario
  parser.py    # parsear_jsonld, parsear_html, PerfilSelectores
  pipeline.py  # Filtro, ejecutar_pipeline, exportar
  cli.py
tests/fixtures # HTML ficticio + perfil.json de ejemplo
```

## Instalación y uso
```bash
pip install -e ".[dev]"
python -m empleos --url "https://sitio-permitido.example/empleos" \
    --perfil tests/fixtures/perfil.json -k python --remoto -o ofertas.csv
```

## Tests
```bash
pytest
```
Todo corre contra fixtures locales y un servidor HTTP en `127.0.0.1`; no se realiza ningún pedido a terceros.

## Limitaciones
- No ejecuta JavaScript: sitios que renderizan en el cliente necesitarían su API.
- Los selectores dependen del HTML de cada sitio y deben mantenerse.
