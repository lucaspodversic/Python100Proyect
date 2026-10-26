# 14 · Sistema de recomendación de películas

Sugiere películas a cada usuario según sus calificaciones previas, con **filtrado colaborativo** implementado desde cero con numpy.

## Qué demuestra
- Tres modelos de complejidad creciente:
  - **Baseline de sesgos**: `μ + b_u + b_i` por mínimos cuadrados alternados.
  - **Item-KNN**: similitud coseno sobre residuos, con *shrinkage* y k vecinos, vectorizado.
  - **Factorización matricial** con sesgos, entrenada por SGD (estilo Funk-SVD).
- Arranque en frío con **promedio bayesiano** (populares sin sesgo por pocos votos).
- Evaluación con RMSE (precisión de la nota) y precision@k (calidad del ranking), comparada contra la media global y contra el azar.
- Verificación semántica: las películas "similares" pertenecen al mismo género latente.

Resultados típicos con los datos sintéticos (200 usuarios, 50 películas):

| modelo | RMSE |
|---|---|
| media global | ≈ 1,51 |
| baseline | ≈ 1,47 |
| item-KNN | ≈ 0,72 |
| factorización | ≈ 0,74 |

## Arquitectura
```
src/recomendador/
├── datos.py       # Calificaciones (matriz), generar_calificaciones(), dividir()
├── modelos.py     # BaselineSesgos, ItemKNN, FactorizacionMatricial, recomendar(), populares()
├── evaluacion.py  # rmse(), precision_at_k()
└── cli.py
```

## Instalación
```bash
pip install -e ".[dev]"
```

## Uso
```bash
recomendador evaluar
recomendador recomendar U007 --modelo mf -n 10
recomendador similares "Terror 03"
recomendador recomendar U1 --csv ratings.csv      # columnas usuario,pelicula,nota
```
Para usar **MovieLens** (descarga manual desde grouplens.org), renombrá `userId,movieId,rating` a `usuario,pelicula,nota`.

## Tests
```bash
pytest
```

## Limitaciones
- La matriz es densa en memoria: sirve hasta decenas de miles de usuarios/películas. Para más, usar matrices dispersas (`scipy.sparse`) o librerías como `implicit` o `surprise`.
- El SGD está escrito en Python puro (didáctico), así que es lento en datasets grandes.
- No usa contenido (género, sinopsis); un modelo híbrido mejoraría el arranque en frío de películas nuevas.
