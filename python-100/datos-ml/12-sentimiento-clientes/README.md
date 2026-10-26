# 12 · Análisis de sentimiento de feedback de clientes

Clasifica reseñas o comentarios en **positivo**, **negativo** o **neutro**, pensado para español informal (rioplatense incluido).

## Qué demuestra
- Preprocesado específico para español: tildes, alargamientos ("buenísimoooo"), URLs, números y **manejo de la negación** (`no me gustó` → `no no_me no_gusto`).
- `FeatureUnion` de TF-IDF de palabras (1-2 gramas) y de caracteres (3-5 gramas), que tolera errores de tipeo.
- Regresión logística multiclase con `class_weight="balanced"`, probabilidades y umbral de confianza.
- **Evaluación honesta**: se entrena con un corpus sintético y se evalúa con 54 reseñas escritas a mano que el modelo nunca vio (accuracy ≈ 0,81, F1-macro ≈ 0,81).
- Explicabilidad: palabras con más peso por clase.

## Arquitectura
```
src/sentimiento/
├── texto.py    # normalizar()
├── corpus.py   # generar_corpus() + cargar_reseñas_reales() (datos/reseñas_evaluacion.csv)
├── modelo.py   # construir_pipeline(), ClasificadorSentimiento
└── cli.py
```

## Instalación
```bash
pip install -e ".[dev]"
```

## Uso
```bash
sentimiento entrenar                                   # corpus sintético
sentimiento entrenar --csv mis_reseñas_etiquetadas.csv # texto,etiqueta
sentimiento clasificar "Llegó roto, un desastre" "Excelente atención"
sentimiento clasificar --archivo encuesta.csv --columna comentario --salida clasificado.csv
```

## Tests
```bash
pytest
```

## Limitaciones
- El corpus sintético es acotado: para producción, etiquetar algunos cientos de comentarios propios o usar un corpus público (TASS).
- La ironía ("buenísimo, tardó un mes 🙃") y las reseñas mixtas son difíciles para un modelo bolsa-de-palabras. Un siguiente paso sería un transformer en español (p. ej. BETO o RoBERTuito vía `transformers`), que no se incluye por peso.
- Los emojis se descartan en la tokenización.
