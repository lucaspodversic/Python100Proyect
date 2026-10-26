# 65 · Monitor de cambios en páginas web

Revisa periódicamente páginas (o una parte de ellas) y avisa cuando cambian,
mostrando un *diff* legible por consola o webhook (Slack/Discord).

## Qué demuestra
- Comparación robusta: se quita `script`/`style`/comentarios, se puede vigilar sólo un **selector CSS**
  y descartar ruido con regex (`--ignorar "\d+ visitas"`).
- Huella SHA-256 + `difflib.unified_diff` con conteo de líneas agregadas/quitadas.
- **Pedidos condicionales** (`ETag`/`If-None-Match`, `Last-Modified`): con 304 no se descarga de nuevo.
- Cliente educado: robots.txt, User-Agent honesto, intervalo mínimo de 60 s en modo vigilancia.
- Estado persistente en JSON; la primera pasada sólo guarda la línea base.

## Arquitectura
```
monitor_web/
  cliente.py     # ClienteEducado
  extraccion.py  # extraer_texto, huella
  monitor.py     # Objetivo, Cambio, Monitor (revisar, vigilar)
  notificar.py   # NotificadorConsola, NotificadorWebhook
  cli.py
```

## Instalación y uso
```bash
pip install -e ".[dev]"
python -m monitor_web --url https://example.org --selector "main"
python -m monitor_web --config objetivos.json --intervalo 900 --webhook https://hooks.slack.com/services/...
```

## Tests
```bash
pytest
```
Servidor local en `127.0.0.1` cuyo contenido el test va modificando; webhooks con transporte falso.

## Limitaciones
- No ejecuta JavaScript (páginas SPA requieren su API o un navegador headless).
- El estado guarda el texto completo de cada página vigilada.
