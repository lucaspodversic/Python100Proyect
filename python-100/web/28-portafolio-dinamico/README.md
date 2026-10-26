# 28 · Portafolio web personal dinámico

## Qué demuestra
Un portafolio **full-stack con Flask** donde los proyectos se cargan desde
**SQLite**: sitio público con filtro por etiquetas, página de detalle con slug
amigable, **API JSON** pública, formulario de contacto (CSRF + honeypot
anti-spam) y **panel de administración** para gestionar proyectos y leer mensajes.

## Arquitectura
```
portafolio/__init__.py  -> crear_app(): DB, CSRF, rutas públicas, API y admin
portafolio/templates/   -> Jinja2 (base, inicio, detalle, contacto, login, admin)
tests/                  -> tests con el test_client de Flask
```
El administrador es único y su contraseña **no se guarda en el código**: se
configura el hash en `PORTAFOLIO_ADMIN_HASH`. Sin hash, el panel queda deshabilitado.

## Instalación
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Uso
```bash
export PORTAFOLIO_SECRET_KEY="$(python -c 'import secrets;print(secrets.token_hex(32))')"
export PORTAFOLIO_ADMIN=lucas
export PORTAFOLIO_ADMIN_HASH="$(python -c "from werkzeug.security import generate_password_hash as g;print(g('mi-clave'))")"
flask --app "portafolio:crear_app()" run
# Público: http://127.0.0.1:5000/   Admin: /admin/login   API: /api/proyectos
```

## Tests
```bash
pytest
```

## Limitaciones
- Sin subida de imágenes (se puede agregar con almacenamiento externo).
- Plantillas sin estilos (HTML semántico listo para tu CSS).
