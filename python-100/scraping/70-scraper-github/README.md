# 70 · Repositorios en tendencia de GitHub

Lista los repositorios más populares creados en los últimos N días (por lenguaje, tema o estrellas
mínimas) usando la **API REST oficial de GitHub**, con ranking por estrellas/día y export a Markdown/CSV.

## Qué demuestra
- **API oficial en vez de scraping** de github.com/trending: `GET /search/repositories`
  con `created:>=FECHA language:X sort=stars`.
- Paginación (100 por página, tope de 1000 de la búsqueda) con corte al agotarse los resultados.
- Cabeceras recomendadas (`Accept: application/vnd.github+json`, `X-GitHub-Api-Version`),
  token opcional por `GITHUB_TOKEN` (nunca se imprime) y **manejo de rate limit**
  (`x-ratelimit-remaining` / `x-ratelimit-reset`, exit code 4).
- Métrica estrellas/día con mínimo de 1 día; Markdown con escape de `|`.

## Decisión sobre robots.txt
`api.github.com/robots.txt` excluye a los *crawlers*, pero la API REST es un servicio programático
regido por los términos de GitHub y sus límites (búsqueda: 10 pedidos/min sin token, 30/min con token).
Por eso el cliente desactiva la verificación de robots **sólo para el host de la API**, manteniendo
User-Agent identificable (GitHub lo exige), 2 s entre pedidos y respeto del rate limit.

## Arquitectura
```
github_tendencias/
  cliente.py   # ClienteEducado (ErrorHTTP conserva la respuesta para leer cabeceras)
  api.py       # ApiGitHub, Repo, construir_consulta, LimiteExcedido
  ranking.py   # ordenar_por_ritmo, markdown, exportar_csv
  cli.py
```

## Instalación y uso
```bash
pip install -e ".[dev]"
python -m github_tendencias --dias 7 --lenguaje python --cantidad 20 --ritmo
GITHUB_TOKEN=ghp_... python -m github_tendencias --tema cli --min-estrellas 50 --csv tendencias.csv
```

## Tests
```bash
pytest
```
API simulada en `127.0.0.1` (fixtures JSON) y fetchers falsos para token y rate limit.

## Limitaciones
- No es exactamente el "Trending" de GitHub (que no tiene API): mide estrellas totales de repos recientes.
- La API de búsqueda devuelve como máximo 1000 resultados por consulta.
