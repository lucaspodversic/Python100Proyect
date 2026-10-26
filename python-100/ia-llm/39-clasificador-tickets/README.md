# 39 · Clasificador de tickets de soporte

## Qué demuestra
Clasificación de tickets en un conjunto **cerrado** de categorías y
prioridades, con **ruteo a equipos**. El LLM recibe las etiquetas válidas y
ejemplos *few-shot*; su JSON se **valida** (etiqueta permitida + confianza
mínima) y, si no pasa, se usa un **clasificador por palabras clave
ponderadas**. Incluye **evaluación**: exactitud, precisión/recall/F1 por clase,
F1 macro y **matriz de confusión**.

## Arquitectura
```
tickets/clasificador.py -> CATEGORIAS (claves + equipo), por_claves(), clasificar()
tickets/metricas.py     -> reporte(), matriz_confusion(), tabla_matriz()
tickets/llm.py          -> interfaz de LLM (OpenAI / Anthropic / falso)
tests/etiquetados.csv   -> dataset de evaluación de ejemplo
```

## Instalación
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Uso
```bash
python -m tickets "Me cobraron dos veces y es urgente"
python -m tickets --evaluar tests/etiquetados.csv
OPENAI_API_KEY=... LLM_PROVEEDOR=openai python -m tickets --evaluar tests/etiquetados.csv
```

## Tests
```bash
pytest   # LLM falso, sin red
```

## Limitaciones
- El dataset de ejemplo es mínimo (10 tickets): para medir en serio hace falta un set etiquetado real.
- Las palabras clave son en español y hay que mantenerlas a mano; sirven como línea base y como respaldo.
