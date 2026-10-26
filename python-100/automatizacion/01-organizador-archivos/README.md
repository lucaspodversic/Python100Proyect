# 01 · Organizador de archivos inteligente

Script que clasifica y renombra automáticamente miles de archivos en carpetas según su **tipo**, **fecha** o **tamaño**, con *dry-run* y *deshacer*.

## Qué demuestra
- Manejo robusto del sistema de archivos con `pathlib` y `shutil`.
- Separación entre lógica pura (clasificación) y efectos (mover archivos).
- Operaciones seguras: nunca sobrescribe (resuelve colisiones con `nombre (1).ext`), es idempotente y se puede revertir.

## Arquitectura
```
src/organizador/
├── clasificador.py   # reglas puras: categoría por extensión, carpeta por fecha/tamaño, plantillas de nombre
├── organizador.py    # planificar() -> lista de Movimiento; ejecutar() y deshacer() con registro JSON
└── cli.py            # argparse: --modo, --plantilla, --dry-run, --deshacer, -r
```

## Instalación
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Uso
```bash
organizador ~/Descargas --dry-run                       # ver qué haría
organizador ~/Descargas --modo tipo_fecha               # imagenes/2024/03/...
organizador ~/Fotos --modo fecha --plantilla "{fecha}_{indice:04d}"
organizador ~/Descargas --deshacer                      # revierte la última ejecución
```
Variables de plantilla: `{nombre}`, `{ext}`, `{fecha}`, `{categoria}`, `{indice}`.

## Tests
```bash
pytest
```
Usan carpetas temporales (`tmp_path`) y fechas fijas: son offline y deterministas.

## Limitaciones
- La fecha usada es la de modificación (`mtime`); no lee EXIF de fotos (se podría agregar con Pillow).
- `deshacer` sólo revierte la última ejecución registrada.
