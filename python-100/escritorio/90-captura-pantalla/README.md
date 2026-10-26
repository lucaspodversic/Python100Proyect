# 90 · Captura de pantalla con nombre personalizado

App Tkinter que captura la pantalla completa o una región elegida con el ratón. Admite un retardo opcional y guarda la imagen con un **nombre personalizado** o con una **plantilla** (`captura_{fecha:%Y%m%d_%H%M%S}`, `{n:03d}`, `{ancho}x{alto}`).

## Qué demuestra

- **Backends detrás de una interfaz** (`Capturador`):
  - Pillow `ImageGrab` está incluido.
  - `mss` es opcional y más rápido; se usa automáticamente si está instalado.
  - `CapturadorFalso` es sintético y determinista, para los tests.
- **Nombres seguros**:
  - Se quitan los separadores de ruta y los caracteres prohibidos en Windows, así que `../../etc/passwd` no sale de la carpeta.
  - Se evitan los nombres reservados (`CON`, `NUL`…).
  - Nunca se sobrescribe: se añade `-2`, `-3`…
- **Guardado atómico** (temporal + `os.replace`) en PNG, JPG, WEBP o BMP.
- **Selección de región** con una capa semitransparente a pantalla completa. Se puede arrastrar en cualquier dirección (`Region.desde_puntos` normaliza) y Esc cancela.
- **La propia ventana se oculta** antes de capturar, para que no aparezca en la imagen.
- Lógica separada de la vista: `capturador.py` y `archivos.py` no importan Tkinter.

## Arquitectura

```
captura/
├── capturador.py  # Region, Capturador (Protocol), CapturadorPillow, CapturadorMss, CapturadorFalso
├── archivos.py    # sanear, generar_nombre, ruta_libre, guardar, Sesion (historial)
└── gui.py         # SelectorRegion (capa), AppCaptura y main()
```

## Instalación y uso

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # opcional: pip install -e ".[mss]"
python -m captura                # guarda en ~/Capturas
python -m captura --demo         # usa el capturador falso
```

## Tests

```bash
pytest
```

- Toda la lógica se prueba con el capturador falso.
- Los tests de la GUI (captura y selector de región, simulando los eventos) se omiten si no hay `DISPLAY`.
- Durante el desarrollo también se verificó manualmente la captura real con Pillow en X11 (Xvfb).

## Limitaciones

- En **Wayland**, `ImageGrab` y `mss` suelen no funcionar o capturar en negro: el compositor exige usar el portal de escritorio (xdg-desktop-portal). En macOS hay que conceder el permiso de «Grabación de pantalla».
- Con varios monitores con distinto escalado (HiDPI), las coordenadas de Tk y las de la captura pueden no coincidir exactamente.
- La transparencia de la capa depende del gestor de ventanas.
- No incluye anotaciones (flechas, texto), copia al portapapeles ni grabación de vídeo.
