# 11 · Predictor de precios de vivienda

Modelo de **regresión** que estima el precio de una casa según barrio, m², ambientes, baños, antigüedad, cochera y distancia al subte.

## Qué demuestra
- `Pipeline` + `ColumnTransformer` (escalado y one-hot) sin *data leakage*.
- Objetivo en escala logarítmica (`TransformedTargetRegressor`) para precios asimétricos.
- Comparación de modelos (Ridge, Random Forest, Gradient Boosting) con validación cruzada.
- Métricas MAE, RMSE, MAPE y R², importancia de variables y persistencia con `joblib`.
- Tests que verifican **relaciones** aprendidas (más m² ⇒ más caro, etc.), no sólo números.

## Arquitectura
```
src/vivienda/
├── datos.py   # generar_dataset() sintético y reproducible; BARRIOS, COLUMNAS
├── modelo.py  # construir_pipeline(), comparar_modelos(), Predictor (entrenar/predecir/guardar/cargar)
└── cli.py
```

## Instalación
```bash
pip install -e ".[dev]"
```

## Uso
```bash
vivienda entrenar --comparar                      # datos sintéticos
vivienda entrenar --csv mis_casas.csv --modelo bosque
vivienda predecir --m2 80 --ambientes 3 --banos 1 --antiguedad 20 --cochera 1 --distancia 0.5 --barrio Norte
```
El CSV debe tener las columnas `m2, ambientes, banos, antiguedad, cochera, distancia_subte_km, barrio, precio`.

## Tests
```bash
pytest
```

## Limitaciones
- Los datos son sintéticos: las métricas no representan un mercado real. Con datos reales (Properati, Zonaprop, California Housing) hay que limpiar outliers, avisos duplicados y moneda.
- `joblib.load` ejecuta código: sólo cargar modelos de origen confiable.
- No modela ubicación fina (lat/lon); un siguiente paso sería *target encoding* geográfico o KNN espacial.
