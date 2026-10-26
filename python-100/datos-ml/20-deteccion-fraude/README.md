# 20 · Detección de fraude (clases desbalanceadas + umbral por costo)

Clasificador de transacciones con tarjeta en las que sólo **~1 % es fraude**. Muestra por qué la exactitud engaña, cómo tratar el desbalance y cómo elegir el **umbral de decisión con criterio de negocio** (costo esperado o recall mínimo).

## Qué demuestra
- **Paradoja de la exactitud.** El baseline "nunca es fraude" tiene un 99 % de exactitud y no detecta nada. Por eso la métrica principal es **PR-AUC** (*average precision*).
- **Desbalance con pesos de clase**: `class_weight="balanced"` en la logística y `sample_weight` en HistGradientBoosting. No se sobremuestrea ni se agregan dependencias.
- **Partición 60/20/20 estratificada.** El umbral se ajusta en la **validación** y se reporta en el **test**, para no hacer trampa.
- **Dos criterios para el umbral** (`umbral.py`):
  - *mínimo costo*: un fraude no detectado cuesta su monto, cada alerta cuesta una revisión de $5 y cada falso positivo suma $10 de fricción con el cliente;
  - *recall mínimo*: el mayor umbral que atrapa al menos un X % del fraude.
- **Datos sintéticos con solapamiento realista**: el fraude es más nocturno, más online, de montos más altos y con dispositivo nuevo, pero muchas compras legítimas también lo son.

## Resultados (`deteccion-fraude comparar`, 30.000 transacciones, test = 6.000)

| Modelo | Exactitud | PR-AUC | Recall | Precisión | Costo $ |
|---|---|---|---|---|---|
| Nunca fraude | 0.990 | 0.010 | 0.00 | 0.00 | 7.448 |
| Logística @0.5 | 0.874 | 0.531 | 0.88 | 0.07 | 11.929 |
| Logística @umbral costo (0.87) | 0.978 | 0.531 | 0.66 | 0.26 | 3.209 |
| Boosting @0.5 | 0.956 | 0.580 | 0.80 | 0.16 | 4.894 |
| **Boosting @umbral costo (0.89)** | 0.990 | 0.580 | 0.53 | 0.49 | **2.507** |

Con umbral 0.5 y pesos balanceados, la logística genera tantas falsas alarmas que **cuesta más que no hacer nada**. Ajustar el umbral reduce el costo un 66 % frente al baseline.

## Arquitectura
```
src/fraude/
├── datos.py   # generar_transacciones(): patrones plantados + solapamiento
├── umbral.py  # Costos, costo_total(), umbral_minimo_costo(), umbral_para_recall()
├── modelo.py  # construir(), DetectorFraude, dividir(), comparar()
└── cli.py
```

## Instalación y uso
```bash
pip install -e ".[dev]"
deteccion-fraude comparar
deteccion-fraude entrenar --salida detector.joblib --criterio recall --recall-min 0.85
deteccion-fraude puntuar --modelo detector.joblib nuevas.csv --salida puntuadas.csv
```

## Tests
```bash
pytest
```
Cubren:
- la prevalencia y el determinismo;
- la función de costo y los umbrales, **calculados a mano**;
- la paradoja de la exactitud;
- la mejora por umbral en test;
- el criterio de recall en validación y en test;
- los errores, la persistencia y la CLI.

## Limitaciones
- Los datos son sintéticos e i.i.d. En la realidad el fraude cambia con el tiempo (*concept drift*). Habría que validar con una partición **temporal** y reentrenar periódicamente.
- Faltan atributos de comportamiento agregados por cliente y comercio (ventanas móviles), que en producción suelen ser los más predictivos.
- Las probabilidades con pesos balanceados **no están calibradas**. Si se necesitan probabilidades reales, usar `CalibratedClassifierCV`.
- `joblib.load` usa pickle: cargá sólo modelos propios.
