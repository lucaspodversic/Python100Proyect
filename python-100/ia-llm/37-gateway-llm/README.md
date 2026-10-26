# 37 · Gateway unificado de LLMs

## Qué demuestra
Un **API gateway** (FastAPI) que expone una sola API para varios proveedores de
LLM (OpenAI, Anthropic, falso) con las funciones típicas de producción:

- **Aliases de modelo** con cadena de **fallback** entre proveedores.
- **Reintentos** con *backoff* exponencial (función de espera inyectable).
- **Caché LRU** de respuestas deterministas (temperatura 0).
- **Rate limiting** por cliente (*token bucket*) → HTTP 429 con `Retry-After`.
- **Autenticación** por clave del gateway (guardadas solo como SHA-256, comparación en tiempo constante).
- **Medición de uso**: pedidos, tokens estimados y costo por cliente.

Las claves de los proveedores viven solo en el servidor (variables de entorno).

## Arquitectura
```
gateway/llm.py     -> adaptadores OpenAI / Anthropic (httpx) + ProveedorFalso
gateway/nucleo.py  -> Gateway (ruteo, fallback, reintentos, caché, uso), CacheLRU, LimitadorTasa
gateway/app.py     -> capa HTTP: /v1/chat, /v1/modelos, /v1/uso, /salud
```

## Instalación
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Uso
```bash
export GATEWAY_CLAVES=clave-cliente-1,clave-cliente-2
export OPENAI_API_KEY=...        # opcional; sin claves usa el proveedor falso
uvicorn gateway.app:app
curl -X POST localhost:8000/v1/chat -H 'Authorization: Bearer clave-cliente-1' \
     -H 'content-type: application/json' -d '{"modelo":"eco","mensajes":[{"rol":"user","contenido":"Hola"}]}'
```

## Tests
```bash
pytest   # proveedores falsos y httpx.MockTransport: sin red ni claves reales
```

## Limitaciones
- Sin *streaming* (SSE); caché, cuotas y uso están en memoria (en producción, Redis).
- Los tokens se estiman (~4 caracteres/token); para facturar, usar el conteo que devuelve cada proveedor.
