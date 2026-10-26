# 13 · Segmentación de clientes (clustering)

Agrupa a los clientes de una tienda según su comportamiento de compra (**RFM**: recencia, frecuencia, monto) con **K-Means**, nombra cada segmento y sugiere una campaña.

## Qué demuestra
- Ingeniería de variables RFM a partir de transacciones crudas (ignora devoluciones).
- `log1p` + `StandardScaler` para que la distancia euclídea no quede dominada por el gasto.
- Elección de *k* con coeficiente de silueta (y por qué no conviene seguirlo a ciegas).
- Nombres de segmento automáticos (Campeones / Leales / Potenciales / Dormidos) y campaña sugerida.
- Validación objetiva: los datos sintéticos tienen 4 perfiles reales y se mide la recuperación con *Adjusted Rand Index* (> 0,7).
- Asignación de clientes nuevos a segmentos ya aprendidos.

## Arquitectura
```
src/segmentacion/
├── datos.py       # generar_transacciones() con perfiles latentes
├── rfm.py         # calcular_rfm()
├── clustering.py  # elegir_k(), Segmentador (ajustar/asignar/resumen), CAMPAÑAS
└── cli.py
```

## Instalación
```bash
pip install -e ".[dev]"
```

## Uso
```bash
segmentacion --demo
segmentacion transacciones.csv --k auto --salida segmentos.csv   # columnas cliente,fecha,monto
```

## Tests
```bash
pytest
```

## Limitaciones
- K-Means asume clusters "esféricos" de tamaño parecido. Con datos reales conviene probar también GMM o clustering jerárquico.
- Los nombres de segmento se asignan con una heurística sobre las medianas. Con k ≠ 4 hay que revisarlos a mano.
- Los datos son sintéticos; con datos reales hay que tratar outliers (clientes mayoristas) por separado.
