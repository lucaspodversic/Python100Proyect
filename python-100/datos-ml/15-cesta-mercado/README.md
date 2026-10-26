# 15 · Análisis de cesta de mercado

Identifica qué productos se compran juntos con frecuencia y traduce las reglas en sugerencias de **disposición de la tienda** y de **promociones cruzadas**.

## Qué demuestra
- **Apriori implementado a mano**: *join* + *prune* por la propiedad anti-monótona, y conteo eligiendo el recorrido más barato.
- Reglas de asociación con soporte, confianza, **lift**, leverage y conviction.
- Corrección verificada **contra fuerza bruta** (todas las combinaciones) y contra el ejemplo de libro pañales/cerveza.
- Datos sintéticos con asociaciones "plantadas" (fernet → coca + hielo, fideos → salsa + queso…), y el algoritmo las encuentra sin falsos positivos.

## Arquitectura
```
src/cesta/
├── apriori.py      # apriori(), generar_reglas(), Regla
├── datos.py        # generar_tickets(), cargar_tickets() (CSV ticket,producto)
├── sugerencias.py  # sugerencias_layout()
└── cli.py
```

## Instalación
```bash
pip install -e ".[dev]"
```

## Uso
```bash
cesta --demo
cesta ventas.csv --soporte 0.01 --confianza 0.3 --salida reglas.csv
```

## Tests
```bash
pytest
```

## Limitaciones
- Apriori recorre los datos una vez por nivel. Con millones de tickets conviene FP-Growth (p. ej. `mlxtend`) o un enfoque en Spark.
- Soporte bajo combinado con un catálogo grande produce una explosión de candidatos; empezar con soporte alto y bajarlo de a poco.
- Que dos productos se compren juntos no implica causalidad. Validar los cambios de góndola con un test A/B.
