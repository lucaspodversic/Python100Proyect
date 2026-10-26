# 96 · Visualizador de algoritmos de ordenamiento

App de escritorio (Tkinter) que anima 7 algoritmos de ordenamiento con barras
de colores, contadores de comparaciones/intercambios/escrituras y control de
velocidad, paso a paso o en reproducción continua.

## Qué demuestra

- **Generadores como corrutinas de animación**: cada algoritmo es un
  generador que cede un `Paso` (comparar, intercambiar, escribir, ordenado)
  y ordena in situ; la GUI consume pasos con `after()` sin hilos ni bloqueos.
- Separación estricta lógica/GUI: `Reproductor` mantiene su propia réplica del
  arreglo aplicando los pasos, lo que permite testearlo sin Tk.
- Implementaciones cuidadas: burbuja con corte temprano, Shell con secuencia
  de Ciura, merge sort bottom-up estable, quicksort con mediana de tres y pila
  explícita (sin recursión profunda), heapsort.

## Arquitectura

```
ordenvis/
├── algoritmos.py   # Paso, generadores, ALGORITMOS, COMPLEJIDAD, aplicar()
├── reproductor.py  # arreglo_aleatorio (aleatorio/casi/invertido/pocos), Reproductor, Estadisticas
└── gui.py          # AppOrden: Canvas + controles; importable sin display
```

Colores: azul = en reposo, amarillo = comparación, rojo = intercambio,
violeta = escritura (merge), verde = posición definitiva.

## Instalación y uso

```bash
pip install -e .          # sin dependencias (Tkinter viene con Python;
                          # en Debian/Ubuntu: sudo apt install python3-tk)
python -m ordenvis
```

Elegí algoritmo y disposición inicial, ajustá `n` y apretá **Nuevo**. Cambiar
el algoritmo reinicia con el **mismo** arreglo, ideal para comparar.

## Tests

```bash
pip install pytest && python -m pytest
```

Cada algoritmo se prueba contra 8 casos (vacío, uno, repetidos, ordenado,
invertido, aleatorios): el arreglo queda ordenado **y** reproducir los pasos
sobre una copia da el mismo resultado (los pasos son fieles). También se
verifican índices válidos, marcas de "ordenado", conteos conocidos, estabilidad
de merge y que los O(n log n) comparan mucho menos que los cuadráticos. El test
de humo de la GUI se omite si no hay `DISPLAY`.

## Limitaciones

- Con `n` grande (cientos) y velocidad baja, los cuadráticos tardan mucho: es
  intencional, para que se note la diferencia.
- Se redibuja el Canvas completo en cada cuadro; suficiente hasta ~300 barras.
- Sin sonido ni comparación lado a lado de dos algoritmos simultáneos.
