# 17 · Predictor de duración de entregas

Estima cuántos minutos tarda un pedido de delivery **y además da un intervalo** ("entre 27 y 35 min"). Usa Gradient Boosting con pérdida Huber para el estimado y modelos de cuantiles para p10/p90.

## Qué demuestra
- **Ingeniería de atributos**:
  - hora cíclica (sin/cos);
  - indicadores de hora pico y de fin de semana;
  - One-Hot para clima y vehículo.
  Todo dentro de un `Pipeline`, así no hay fuga de datos.
- `GradientBoostingRegressor(loss="huber")` para el estimado, que es robusto a la cola pesada de demoras.
- **Intervalos de predicción** con `loss="quantile"` (α = 0.1 y 0.9). Se ordenan para evitar el cruce de cuantiles.
- Evaluación honesta frente a baselines (media y regresión lineal) y medición de la **cobertura real** del intervalo.
- Datos sintéticos con un proceso generador conocido (`datos.py`). Los tests verifican relaciones que tienen sentido: más distancia, tormenta, bici u hora pico implican más tiempo.

## Resultados (3000 pedidos, 25 % test)

| Modelo | MAE (min) |
|---|---|
| Media | 7.41 |
| Regresión lineal | 2.36 |
| **Gradient Boosting** | **1.29** |

El intervalo p10–p90 cubre el **72 %** (nominal 80 %), con un ancho medio de 4.7 min. Los cuantiles de boosting suelen quedar algo estrechos; ver las limitaciones.

## Arquitectura
```
src/entregas/
├── datos.py   # generar_pedidos(): proceso generador (trayecto/velocidad, clima, congestión, cola, ruido)
├── modelo.py  # PredictorEntregas (medio + p10 + p90), evaluar()
└── cli.py
```

## Instalación y uso
```bash
pip install -e ".[dev]"
predictor-entregas evaluar
predictor-entregas entrenar --salida modelo.joblib
predictor-entregas predecir --modelo modelo.joblib --distancia 4.2 --hora 21 --clima lluvia --vehiculo moto
```

## Tests
```bash
pytest
```
Cubren el determinismo, la mejora frente a los baselines, la cobertura del intervalo, la dirección de los efectos, la importancia de atributos, la persistencia y la CLI.

## Limitaciones
- Los datos son sintéticos. Con datos reales faltarían el tráfico en vivo, la ubicación exacta y el historial del restaurante y del repartidor.
- El intervalo queda algo por debajo de lo nominal. Para una cobertura garantizada convendría usar *conformal prediction* (p. ej. MAPIE).
- `joblib.load` usa pickle: cargá sólo modelos propios.
