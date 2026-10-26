# 97 · Detector de objetos (YOLO) con interfaz intercambiable

Detección de objetos en imágenes con **YOLO (ultralytics)** detrás de una
interfaz `Detector`, más un **detector falso determinista** para desarrollar y
testear sin GPU, sin pesos y sin Internet. Incluye NMS, filtros, anotación de
imágenes, exportación JSON y un rastreador simple por IoU con conteo de cruces
de línea (base para contar personas/autos en video).

## Qué demuestra

- Diseño por **Protocol** (inyección de dependencias): el post-proceso, el
  dibujo, el CLI y el seguimiento no saben qué backend detecta.
- Import perezoso de dependencias pesadas (ultralytics/torch) con error claro.
- Algoritmos clásicos de visión: IoU, Non-Maximum Suppression voraz por clase,
  componentes conexas (BFS), seguimiento estilo SORT sin Kalman.

## Arquitectura

```
detector/
├── modelo.py        # Caja, Deteccion, Detector (Protocol), DetectorYOLO, DetectorFalso
├── postproceso.py   # iou, nms, filtrar, contar
├── seguimiento.py   # Rastreador (IoU 1-a-1 voraz) + cruces de una línea horizontal
├── dibujo.py        # anotar(): cajas y etiquetas con color estable por clase
└── cli.py           # imagen | carpeta | demo → PNG anotados + detecciones.json
```

El detector falso reconoce colores puros: rojo → `persona`, azul → `auto`,
verde → `perro`. La confianza depende de la solidez del blob (área / área de
su caja), así un rectángulo puntúa más que una elipse.

## Instalación y uso

```bash
pip install -e .              # numpy + pillow
python -m detector demo --salida demo/          # escena sintética, sin YOLO

pip install -e '.[yolo]'      # ultralytics (trae torch: descarga grande)
python -m detector fotos/ --salida anotadas/ --conf 0.4 --clases person,car
python -m detector foto.jpg --salida out/ --pesos yolov8n.pt
```

> La primera ejecución con YOLO **descarga los pesos** (`yolo11n.pt`, ~6 MB)
> desde los servidores de Ultralytics. Las clases de los modelos COCO están
> en inglés (`person`, `car`, `dog`…).

## Tests

```bash
pip install pytest && python -m pytest
```

Offline y deterministas: IoU con valores calculados a mano, NMS por clase y
global, filtros, el detector falso sobre la escena demo (cajas exactas),
anotación (color del borde), el rastreador (IDs estables, cruce de línea,
olvido de pistas) y el CLI. ultralytics **no** se instala ni se usa: se
verifica solo que, si falta, el error sea claro.

## Limitaciones

- Sin video en el CLI (el `Rastreador` está listo para usarse con OpenCV,
  pero leer cuadros queda fuera del alcance).
- El rastreador no predice movimiento (sin Kalman): con objetos rápidos o
  baja tasa de cuadros el IoU entre cuadros cae y se crean IDs nuevos.
- El detector falso es una herramienta de test, no un detector real.
- Usar detección de personas en espacios públicos puede tener implicancias
  legales de privacidad: informate antes de desplegarlo.
