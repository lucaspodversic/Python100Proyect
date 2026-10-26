# 86 · Conversor de unidades (Tkinter)

Conversor de escritorio entre unidades de **longitud, masa, temperatura**, volumen y tiempo. Convierte en vivo mientras escribís y muestra además una tabla con el valor en todas las unidades de la magnitud.

## Qué demuestra

- **Aritmética exacta con `fractions.Fraction`**: los factores se escriben como texto (`"0.0254"`), así que 1 pulgada da exactamente 2,54 cm. Ir y volver entre cualquier par de unidades devuelve exactamente el valor original (está testeado para todos los pares).
- **Modelo afín** `base = valor·factor + desplazamiento`: la temperatura (°C, °F, °R → K) entra en el mismo esquema que las demás magnitudes, sin casos especiales.
- **Validación física**: no se aceptan temperaturas bajo el cero absoluto ni masas, longitudes o volúmenes negativos. El tiempo sí puede ser negativo, porque es relativo.
- **Entrada tolerante pero no ambigua**: acepta `1,5`, `1 000.25` y `-2e3`. Rechaza `1.234,5`, porque no se puede saber cuál es el separador decimal, y también `inf` y `nan`.
- **Formato**: 10 cifras significativas, sin ceros sobrantes y en notación científica cuando hace falta.
- **Separación lógica / vista**: `unidades.py` es puro; la GUI solo reacciona a `trace_add`.

## Arquitectura

```
conversor/
├── unidades.py  # Unidad, MAGNITUDES, parsear, convertir, formatear, tabla_conversiones
└── gui.py       # AppConversor (Combobox + Entry + Treeview) y main()
```

Para agregar una unidad alcanza con sumar una línea en `MAGNITUDES`.

## Instalación y uso

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m conversor
```

## Tests

```bash
pytest
```

El test de humo de la GUI se omite sin `DISPLAY` (en un servidor: `xvfb-run pytest`).

## Limitaciones

- Las unidades de volumen de cocina son las de EE. UU. (la *cup* imperial es distinta).
- No convierte entre magnitudes (por ejemplo, volumen ↔ masa según la densidad) ni unidades compuestas como km/h.
