# 38 · Monitor de sentimiento en redes (casi) en tiempo real

## Qué demuestra
Un monitor que sondea **fuentes intercambiables** (archivo local, Reddit,
X/Twitter) detrás de la interfaz `FuenteFeed`, **deduplica**, clasifica el
sentimiento **por lotes con un LLM** (JSON validado) con **léxico de respaldo**
(con manejo de negaciones), mantiene una **ventana deslizante temporal** y
dispara **alertas** con mínimo de muestras y período de enfriamiento.

## Arquitectura
```
sentimiento/fuentes.py     -> Publicacion, FuenteFeed, FuenteArchivo / FuenteReddit / FuenteTwitter
sentimiento/analizador.py  -> lexico(), clasificar() (LLM por lotes + respaldo)
sentimiento/monitor.py     -> Monitor (ciclo, ventana, métricas, alertas)
sentimiento/llm.py         -> interfaz de LLM (OpenAI / Anthropic / falso)
```
Una fuente que falla no detiene el monitor; los clientes HTTP son inyectables.

## Instalación
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Uso
```bash
python -m sentimiento tests/feed.jsonl AcmeBank 3      # demo local, sin red
```
Para fuentes reales: `X_BEARER_TOKEN` (API v2 de X) y, para el LLM, `OPENAI_API_KEY`
+ `LLM_PROVEEDOR=openai`. Respetá los términos de uso y límites de cada API.

## Tests
```bash
pytest   # fixtures JSONL y httpx.MockTransport: sin red ni tokens
```

## Limitaciones
- "Tiempo real" por sondeo periódico (polling), no por streaming.
- El léxico de respaldo es básico (no detecta ironía); el estado del monitor vive en memoria.
