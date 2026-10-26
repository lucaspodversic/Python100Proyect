# 60 · Generador de memes

Agrega texto superior e inferior estilo meme (blanco, mayúsculas, contorno negro) a cualquier imagen.

## Qué demuestra
- Pillow: `ImageDraw.text` con `stroke_width`/`stroke_fill` para el contorno.
- *Word wrap* medido en **píxeles** y reducción automática del tamaño de fuente
  hasta que el bloque entre en el 30 % del alto.
- Búsqueda de fuente: Impact → DejaVu Sans Bold → fuente escalable integrada de Pillow.
- Cargador de fuentes inyectable para tests deterministas.

## Arquitectura
```
memes/
  componer.py  # cargar_fuente, ajustar_texto, crear_meme, EstiloMeme
  cli.py
```

## Instalación y uso
```bash
pip install -e ".[dev]"
python -m memes gato.jpg -a "cuando el código compila" -b "a la primera"
python -m memes foto.png -b "sólo abajo" -o salida.jpg --fuente /ruta/Impact.ttf
```

## Tests
```bash
pytest
```
Usa imágenes generadas en memoria y verifica colores por región.

## Limitaciones
- La apariencia exacta depende de la fuente instalada (Impact no viene en Linux por defecto).
- Sin plantillas descargadas: usá tus propias imágenes o imágenes con licencia libre.
