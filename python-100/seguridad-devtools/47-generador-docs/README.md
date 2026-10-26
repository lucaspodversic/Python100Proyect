# 47 · Generador de documentación automática

Lee los docstrings de tu código y genera documentación en **Markdown** o **HTML**.

## Qué demuestra
- Extracción vía `ast` (no importa ni ejecuta tu código: seguro y sin dependencias).
- Reconstrucción de firmas con anotaciones (`ast.unparse`), async y decoradores.
- HTML autocontenido con escape de todo el texto (evita inyección de marcado).

## Arquitectura
```
autodoc/
  extractor.py  # Modulo / Clase / Funcion, extraer_modulo, extraer_paquete
  render.py     # a_markdown, a_html
  cli.py
```

## Instalación y uso
```bash
pip install -e ".[dev]"
python -m autodoc mi_paquete/ -f md -o docs/API.md
python -m autodoc mi_paquete/ -f html -o docs/index.html --titulo "Mi API"
```

## Tests
```bash
pytest
```

## Limitaciones
- No interpreta formatos de docstring (Google/NumPy/reST): los muestra tal cual.
- No resuelve herencia ni referencias cruzadas (para eso: Sphinx, pdoc, mkdocstrings).
