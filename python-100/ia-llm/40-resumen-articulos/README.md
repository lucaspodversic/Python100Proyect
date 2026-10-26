# 40 · Resumidor de artículos web

## Qué demuestra
De URL a resumen: **obtención** segura (solo http/https, tope de tamaño,
verificación de Content-Type), **extracción del contenido principal** con
`html.parser` de la biblioteca estándar (metadatos og/autor/fecha, prioriza
`<article>`, descarta nav/aside/footer/form/scripts), **resumen map-reduce**
con LLM para textos largos y **resumen extractivo** de respaldo (frecuencia de
palabras) cuando no hay LLM o falla.

## Arquitectura
```
resumen/obtencion.py  -> Fetcher (Protocol), FetcherHTTP, FetcherFalso (fixtures)
resumen/extraccion.py -> extraer() -> Articulo (titulo, autor, fecha, parrafos)
resumen/resumidor.py  -> resumir() (llm | llm-mapreduce | extractivo), a_markdown()
resumen/llm.py        -> interfaz de LLM (OpenAI / Anthropic / falso)
```

## Instalación
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Uso
```bash
python -m resumen tests/articulo.html                 # archivo local, resumen extractivo
OPENAI_API_KEY=... LLM_PROVEEDOR=openai python -m resumen https://sitio/articulo
```

## Tests
```bash
pytest   # HTML de fixture local y httpx.MockTransport: sin red
```

## Limitaciones
- No ejecuta JavaScript: sitios que cargan el contenido dinámicamente o con paywall no se extraen bien.
- La heurística de contenido es simple comparada con librerías como readability/trafilatura.
- `FetcherHTTP` no bloquea IPs privadas (SSRF): si se expone como servicio, agregar esa validación.
