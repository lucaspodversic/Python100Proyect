# 84 · Visor de imágenes (Tkinter + Pillow)

Visor de escritorio para PNG, JPEG, GIF, BMP, WebP y TIFF. Navega la carpeta, hace zoom (botones, teclas o rueda), ajusta a la ventana, rota, refleja, pasa a modo presentación y guarda una copia transformada.

## Qué demuestra

- **Separación lógica / vista**:
  - `nucleo.py` opera solo con `PIL.Image` y números (galería, zoom, transformaciones), así que se testea sin pantalla.
  - `gui.py` solo convierte el resultado a `ImageTk.PhotoImage` y guarda una referencia viva, porque si no Tk borra la imagen.
- **Orientación EXIF**: las fotos de móvil se muestran derechas gracias a `ImageOps.exif_transpose`.
- **Transformaciones sin pérdida**: `transpose` en pasos de 90°, sin interpolar. Al reducir se usa LANCZOS; al ampliar ×4 o más, NEAREST, para ver los píxeles.
- **Seguridad y robustez**:
  - `Image.MAX_IMAGE_PIXELS` limita las *decompression bombs*.
  - Los archivos corruptos se omiten y se quitan de la galería sin cortar la navegación.
  - Al guardar en JPEG se quita el canal alfa.
- **Orden natural**: `img2` va antes que `img10`.
- **Zoom acotado** entre 5 % y 1600 %. "Ajustar" no amplía las imágenes chicas.

## Arquitectura

```
visor/
├── nucleo.py  # listar, abrir, info, zoom_ajustado, Galeria, Vista, guardar_transformada
└── gui.py     # AppVisor (Canvas + barra) y main()
```

## Instalación y uso

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m visor ~/Imágenes/foto.jpg     # o una carpeta
```

Teclas: ← → para navegar, `+` `-` para el zoom, `r` para rotar, espacio para la presentación y Ctrl+O para abrir.

## Tests

```bash
pytest
```

Las imágenes de prueba se generan en `tmp_path` durante el test, incluida una con EXIF de rotación. El test de humo de la GUI se omite sin `DISPLAY` (en un servidor: `xvfb-run pytest`).

## Limitaciones

- Los GIF animados muestran solo el primer cuadro.
- No hay arrastre (*pan*) con el ratón al hacer zoom: la imagen queda centrada.
- Las imágenes muy grandes se re-escalan completas en cada zoom. Un visor serio usaría teselas.
