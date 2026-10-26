# 29 · Foro de discusión (tipo Reddit)

## Qué demuestra
API de foro con **FastAPI + SQLite**: registro/login con **scrypt** y tokens
Bearer (en la base se guarda solo su SHA-256, con vencimiento), hilos,
**respuestas anidadas** en árbol, **votos** únicos por usuario (cambiables o
anulables), tres rankings (`nuevos`, `top` y `populares` con una fórmula *hot*
al estilo Reddit) y borrado lógico que no rompe el árbol de la conversación.

## Arquitectura
```
foro/seguridad.py -> hash scrypt (stdlib), tokens y su huella SHA-256
foro/ranking.py   -> fórmula "hot" (log del puntaje + recencia)
foro/app.py       -> crear_app(): auth, hilos, respuestas, votos (reloj inyectable)
tests/            -> tests de seguridad, ranking y API
```

## Instalación
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Uso
```bash
FORO_DB=foro.db uvicorn foro.app:app
TOKEN=$(curl -s -X POST localhost:8000/login -H 'content-type: application/json' -d '{"nombre":"ana","clave":"clave-larga-1"}' | jq -r .token)
curl -X POST localhost:8000/hilos -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' -d '{"titulo":"Hola","texto":"Primer hilo"}'
curl "localhost:8000/hilos?orden=populares"
```

## Tests
```bash
pytest
```

## Limitaciones
- Sin subforos/comunidades ni moderación.
- El puntaje se calcula al vuelo (para gran escala convendría cachearlo).
