# 79 · Plataforma de encuestas

API con **FastAPI + SQLAlchemy + SQLite**: los creadores diseñan encuestas, las comparten por un enlace opaco y analizan los resultados agregados, que pueden exportar a **CSV** o ver como **gráficos PNG** generados con **matplotlib (backend Agg)**.

## Qué demuestra

- Cuatro tipos de pregunta: `unica`, `multiple`, `escala` (1-5) y `texto`, con validación estricta de la definición y de cada respuesta. Por ejemplo, `True` no se acepta como un 1 en la escala.
- **Respuestas anónimas**: no se guarda quién respondió y el endpoint no devuelve un id.
- **Códigos de invitación de un solo uso**:
  - Se guardan hasheados (SHA-256) y no distinguen mayúsculas de minúsculas.
  - Se consumen de forma atómica con `UPDATE … WHERE usado = false`, así que dos envíos simultáneos con el mismo código no pueden pasar ambos.
- Cierre manual o automático por fecha (`cierra_en`), con reloj inyectable.
- **Agregación**: conteo por opción, distribución y promedio de la escala, y listado de textos.
- **CSV seguro**: las celdas que empiezan con `= + - @` se prefijan con `'` para evitar la inyección de fórmulas en planillas.
- **Gráficos**: `matplotlib.use("Agg")` funciona en servidores sin pantalla, y `plt.close(fig)` evita fugas de memoria.
- Los resultados solo los ve el creador (o un admin); a cualquier otro se le responde 404.

## Arquitectura

```
app/
├── modelos.py   # Encuesta, Pregunta (JSON de opciones), Codigo (hash), Respuesta (JSON)
├── servicio.py  # validación, respuesta, agregación, CSV
├── graficos.py  # PNG con matplotlib Agg
└── main.py      # rutas privadas (/encuestas/...) y públicas (/e/{slug})
```

## Instalación y uso

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

1. Registrate e iniciá sesión. Después hacé `POST /encuestas` y compartí `/e/{slug}`.
2. Opcional: `POST /encuestas/{id}/codigos {"cantidad": 50}` para generar y repartir códigos.
3. Mirá `GET /encuestas/{id}/resultados`, el `.csv` o `/preguntas/{pid}/grafico.png`.

## Tests

```bash
pytest
```

## Limitaciones

- Sin códigos, el anonimato impide evitar que una misma persona responda varias veces. Para esos casos están los códigos.
- El orden de inserción de las respuestas, cruzado con los registros del servidor, podría permitir correlacionar respuestas con personas. Para un anonimato fuerte habría que barajar o agrupar las respuestas. El proyecto 98 aborda un caso más estricto.
- No hay lógica condicional (saltar preguntas según respuestas).
