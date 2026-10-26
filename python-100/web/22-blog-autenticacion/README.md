# 22 · Blog con autenticación (Flask)

## Qué demuestra
Un sitio web completo en **Flask** donde los usuarios se registran, inician
sesión y publican/editan/borran sus artículos, aplicando buenas prácticas de
seguridad web:

| Riesgo | Mitigación |
|---|---|
| Robo de contraseñas | Hash `scrypt` con sal (Werkzeug) |
| CSRF | Token por sesión en todos los formularios POST, comparación en tiempo constante |
| XSS | Autoescape de Jinja2 |
| Fijación de sesión | `session.clear()` al iniciar sesión |
| Open redirect | Solo se aceptan rutas internas en `?siguiente=` |
| Escalada horizontal | Solo el autor edita/borra (403 en otro caso) |
| Inyección SQL | Consultas parametrizadas |

## Arquitectura
```
blog/__init__.py    -> crear_app(): config, DB por petición, CSRF, auth y vistas
blog/templates/     -> plantillas Jinja2 (base, auth, inicio, articulo, editar)
tests/              -> tests con el test_client de Flask
```

## Instalación
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Uso
```bash
export BLOG_SECRET_KEY="$(python -c 'import secrets;print(secrets.token_hex(32))')"
export BLOG_DB=blog.db
flask --app "blog:crear_app()" run
```

## Tests
```bash
pytest
```

## Limitaciones
- Sin recuperación de contraseña ni verificación de email.
- Sin limitación de intentos de login (en producción: rate limiting).
- Para producción usar HTTPS y `SESSION_COOKIE_SECURE=True`.
