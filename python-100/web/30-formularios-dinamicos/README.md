# 30 · Generador de formularios dinámicos

## Qué demuestra
Una herramienta tipo Google Forms con **FastAPI + Pydantic + SQLite**: el
usuario define un formulario con un **esquema JSON** (7 tipos de campo con
restricciones), se genera el **HTML automáticamente**, se recogen respuestas
**validadas en el servidor** y el dueño ve un **resumen estadístico** y exporta a **CSV**.

## Arquitectura
```
formularios/esquema.py -> modelos Campo / DefinicionFormulario y validar_respuesta()
formularios/app.py     -> API JSON, HTML generado (/f/{slug}), resumen y export CSV
tests/                 -> tests de esquema, validación y API
```
Seguridad: escape HTML de todo texto del creador (anti-XSS), token de dueño
para ver/exportar/cerrar, y protección contra **inyección de fórmulas** en el CSV.

## Instalación
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Uso
```bash
FORMULARIOS_DB=formularios.db uvicorn formularios.app:app
curl -X POST localhost:8000/api/formularios -H 'content-type: application/json' -d '{
  "titulo":"Encuesta","campos":[{"nombre":"nombre","etiqueta":"Nombre","tipo":"texto","requerido":true},
  {"nombre":"nota","etiqueta":"Nota","tipo":"numero","minimo":1,"maximo":10}]}'
# Abrí en el navegador la url_publica devuelta: http://127.0.0.1:8000/f/<slug>
```

## Tests
```bash
pytest
```

## Limitaciones
- El formulario HTML público no usa CSRF porque no hay sesión (es anónimo, como un Google Form); para evitar spam convendría un captcha o rate limiting.
- Sin lógica condicional entre campos ni edición del formulario después de creado.
