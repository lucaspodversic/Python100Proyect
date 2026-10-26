# 25 · Acortador de URLs

## Qué demuestra
Servicio tipo bit.ly con **FastAPI + SQLite**: códigos cortos aleatorios base62
no enumerables, alias personalizados, vencimiento, redirección 307 con conteo
de clics y estadísticas por día y por sitio de origen (referer).

## Arquitectura
```
acortador/codigos.py -> base62, códigos seguros (secrets), validación de URL y alias
acortador/app.py     -> crear_app(): crear, redirigir, estadísticas y borrar
tests/               -> unitarios + API (con reloj falso inyectable)
```
Seguridad: solo URLs `http/https` (bloquea `javascript:`/`data:`), token de
borrado secreto por enlace, y del referer se guarda solo el host.

## Instalación
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Uso
```bash
ACORTADOR_DB=enlaces.db ACORTADOR_BASE_URL=http://localhost:8000 uvicorn acortador.app:app
curl -X POST localhost:8000/api/enlaces -H 'content-type: application/json' -d '{"url":"https://example.com","alias":"demo"}'
curl -i localhost:8000/demo
curl localhost:8000/api/enlaces/demo
```

## Tests
```bash
pytest
```

## Limitaciones
- Sin cuentas de usuario: la propiedad se prueba con el token de borrado.
- No verifica si el destino es malicioso (en producción: listas de phishing/Safe Browsing).
- Sin rate limiting contra abuso masivo.
