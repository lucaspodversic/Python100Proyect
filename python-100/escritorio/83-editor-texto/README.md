# 83 · Editor de texto (Tkinter)

Editor de texto plano con menús y atajos: nuevo, abrir, guardar, guardar como, recientes, deshacer/rehacer, buscar, reemplazar todo e ir a línea. La barra de estado muestra línea, columna, palabras, caracteres y codificación.

## Qué demuestra

- **Guardado atómico**: se escribe un temporal en la misma carpeta, se hace `fsync` y después `os.replace`. Si falla el disco o se corta la luz, el archivo original queda intacto. También se conservan los permisos del original.
- **Codificaciones**:
  - Detecta el BOM UTF-8; si no lo hay, prueba UTF-8, después cp1252 y por último latin-1.
  - Al guardar se respeta la codificación original y los fines de línea (`\r\n` o `\n`).
- **Protecciones**: rechaza archivos binarios (bytes nulos) y archivos de más de 20 MiB.
- **Búsqueda** literal o por regex, con opciones de mayúsculas y palabra completa:
  - Las regex inválidas producen un error claro, no una excepción.
  - En modo literal, el reemplazo también es literal: `\1` no se interpreta.
  - "Reemplazar todo" se deshace en un solo paso, porque se apagan los `autoseparators` de Tk.
- **Aviso de cambios sin guardar** al abrir otro archivo, crear uno nuevo o cerrar. El título muestra `*` mientras haya cambios.
- **Recientes**: lista MRU persistida en `~/.config/editor-py100/recientes.json`. Si el archivo está corrupto, se ignora.
- **Separación lógica / vista**: `nucleo.py` es puro y testeable. `gui.py` crea la ventana solo en `main()`.

## Arquitectura

```
editor/
├── nucleo.py  # Documento, buscar/reemplazar/siguiente, estadisticas, Recientes
└── gui.py     # AppEditor (Text + menús + diálogos) y main()
```

## Instalación y uso

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m editor [archivo.txt]
```

Atajos: Ctrl+N, Ctrl+O, Ctrl+S, Ctrl+F, Ctrl+H, Ctrl+G, Ctrl+Z y Ctrl+Y.

## Tests

```bash
pytest
```

El test de humo de la GUI abre, busca, reemplaza, guarda y deshace en una ventana real. Si no hay `DISPLAY`, se omite (en un servidor: `xvfb-run pytest`).

## Limitaciones

- Sin pestañas, resaltado de sintaxis ni números de línea.
- La detección cp1252/latin-1 es heurística: un archivo en otra codificación de 8 bits se abrirá como cp1252.
- El widget `Text` de Tk se vuelve lento con archivos de varios MB.
