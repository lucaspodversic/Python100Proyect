# 80 · CMS headless

Gestor de contenidos "headless" (API pura) con **FastAPI + SQLAlchemy + SQLite**. Tiene flujo editorial con roles, slugs únicos, historial de revisiones, **bloqueo optimista**, publicación programada, render seguro de Markdown y subida de imágenes validada.

## Qué demuestra

- **Roles**:
  - `autor`: crea, edita sus borradores y los envía a revisión.
  - `editor`: aprueba o rechaza, publica, archiva, restaura y borra.
  - `admin`: además asigna roles.
- **Flujo editorial**: `borrador → en_revision → publicado → archivado`, con rechazo de vuelta a borrador. Las acciones inválidas responden 409 y las no permitidas para el rol, 403.
- **Slugs**: se quitan las tildes (`¡Hola, Año Nuevo!` → `hola-ano-nuevo`) y se resuelven colisiones con `-2`, `-3`…
- **Bloqueo optimista** (control de concurrencia): `PUT` exige la `version` leída, y `UPDATE … WHERE version = ?` rechaza con 409 si otra persona guardó antes. No se pierden ediciones.
- **Revisiones**: cada versión queda guardada y se puede restaurar (eso crea una versión nueva, no reescribe la historia).
- **Publicación programada** con `publicar_en`, filtrada por el reloj (inyectable en tests).
- **Render seguro**: primero se escapa todo el HTML y después se aplican solo transformaciones conocidas. Los enlaces se limitan a `http(s)` (bloquea `javascript:`).
- **Subida segura de imágenes**:
  - El tipo se detecta por *números mágicos*, no por extensión ni `Content-Type`.
  - Límite de 2 MiB.
  - El archivo se guarda con un nombre aleatorio (sin *path traversal*).
  - Solo se sirven medios registrados en la base, con `X-Content-Type-Options: nosniff`.

## Arquitectura

```
app/
├── contenido.py  # slugs, render Markdown seguro, detección de imágenes (puro)
├── servicio.py   # flujo editorial, bloqueo optimista, revisiones
├── modelos.py    # Articulo(version), Revision, Medio
└── main.py       # /articulos (redacción), /medios, /publico (lectura)
```

## Instalación y uso

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export CMS_ADMIN_PASSWORD="clave-segura"
uvicorn app.main:app --reload   # los medios se guardan en ./medios (ignorado por git)
```

## Tests

```bash
pytest
```

## Limitaciones

- El Markdown es un subconjunto mínimo. Para producción conviene usar `markdown-it-py` junto con un sanitizador como `nh3`.
- No hay redimensionado de imágenes, CDN, comentarios ni internacionalización.
- Los medios se guardan en el disco local; en la nube se usaría almacenamiento de objetos.
