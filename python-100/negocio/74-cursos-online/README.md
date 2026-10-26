# 74 · Plataforma de cursos online

Backend con **FastAPI + SQLAlchemy + SQLite** con roles de profesor y alumno. Incluye cursos, lecciones ordenadas, examen final de opción múltiple corregido automáticamente y seguimiento del progreso hasta el certificado.

## Qué demuestra

- **Autorización por rol y por propiedad**: solo el profesor que creó un curso puede modificarlo. Además, el alumno solo ve las lecciones de los cursos en los que se inscribió.
- **Ciclo de publicación**: no se puede publicar un curso sin lecciones, y un curso sin publicar no aparece en el catálogo ni admite inscripciones.
- **Exámenes**: las preguntas se validan (al menos 2 opciones y un índice correcto válido) y la respuesta correcta **nunca se envía al alumno**. Hay un límite de intentos y no se puede rendir otra vez un examen aprobado.
- **Progreso**: porcentaje de lecciones completadas (marcar dos veces la misma lección no la duplica) y certificado cuando el alumno completa todas las lecciones y aprueba el examen.
- Integridad con restricciones `UNIQUE` (inscripción única, orden de lección único por curso).

## Arquitectura

```
app/
├── modelos.py   # Curso, Leccion, Examen (JSON), Inscripcion, LeccionCompletada, Intento
├── servicio.py  # reglas: autoría, inscripción, corrección, progreso
├── main.py      # rutas + crear_app()
└── auth.py, seguridad.py, db.py
```

## Instalación y uso

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export CURSOS_ADMIN_PASSWORD="clave-segura"
uvicorn app.main:app --reload
```

Flujo: el usuario se registra (queda como alumno) → el admin lo promueve a `profesor` con `PATCH /usuarios/{id}/rol` → el profesor crea el curso, las lecciones y el examen y lo publica → los alumnos se inscriben, cursan y rinden.

## Tests

```bash
pytest
```

## Limitaciones

- Solo hay preguntas de opción múltiple con una única respuesta correcta.
- No hay subida de videos ni archivos: el contenido es texto o Markdown.
- No se exige completar las lecciones en orden.
