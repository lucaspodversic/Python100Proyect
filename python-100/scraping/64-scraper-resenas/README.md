# 64 · Scraper de reseñas de productos (genérico)

Extrae reseñas de páginas de producto, analiza su **sentimiento** y genera un resumen
(promedio de estrellas, distribución, temas que gustan / molestan, contradicciones).

> ⚠️ **Limitación importante / términos de uso**: las *Condiciones de uso* de **Amazon prohíben
> el scraping** y el sitio bloquea bots. Este proyecto **no apunta a Amazon ni a ningún sitio por
> defecto**. Alternativas legítimas:
> - Si sos vendedor: informes y **Selling Partner API** de Amazon para tus propios productos.
> - **Datasets públicos** de reseñas publicados con fines de investigación.
> - Exportaciones de tu propia tienda (`--archivo pagina.html`) o sitios cuyos términos lo permitan.
> - Muchas tiendas publican reseñas como datos estructurados **schema.org `Review`** (soportado).

## Qué demuestra
- Parser genérico: **JSON-LD `Review`** + **selectores CSS** configurables por JSON, con paginación
  y deduplicación entre páginas.
- Normalización de calificaciones (`4,0 de 5 estrellas`, `8/10`, `★★★☆☆`) a escala 1-5.
- **Sentimiento por léxico** explicable (sin descargar modelos): negaciones, intensificadores,
  normalización a [-1, 1].
- Cliente educado (robots.txt, User-Agent honesto, ritmo de 3 s por defecto).

## Arquitectura
```
resenas/
  cliente.py       # ClienteEducado
  modelo.py        # Resena, parsear_estrellas
  parser.py        # parsear_jsonld, parsear_html, PerfilResenas
  sentimiento.py   # puntuar, clasificar
  resumen.py       # resumir, exportar_csv
  cli.py
```

## Instalación y uso
```bash
pip install -e ".[dev]"
python -m resenas --archivo tests/fixtures/resenas1.html --perfil tests/fixtures/perfil.json
python -m resenas --url "https://tienda-permitida.example/p/123/resenas" --perfil perfil.json --csv r.csv
```

## Tests
```bash
pytest
```
Fixtures HTML ficticias + servidor en `127.0.0.1`; ningún pedido a terceros.

## Limitaciones
- El léxico de sentimiento es básico: no detecta ironía ni contexto (por eso se reportan discrepancias).
- No ejecuta JavaScript.
