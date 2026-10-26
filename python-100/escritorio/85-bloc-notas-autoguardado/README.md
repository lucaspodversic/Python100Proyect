# 85 · Bloc de notas con autoguardado (Tkinter)

Bloc de notas de escritorio con lista de notas, buscador, notas fijadas, papelera y **autoguardado**: no hay botón de guardar, porque las notas se guardan solas.

## Qué demuestra

- **Autoguardado con *debounce* y plazo máximo**:
  - Se guarda cuando el usuario deja de escribir durante 1,5 s.
  - Si escribe sin parar, se guarda igual cada 10 s.
  - Además se guarda al cambiar de nota, al fijar y al cerrar la ventana.
  - La política (`Autoguardado`) es pura y se testea con un reloj falso, sin esperas reales.
- **Escritura atómica**: temporal, `fsync` y `os.replace`. Si el guardado falla, por ejemplo con el disco lleno, la versión anterior queda intacta, se avisa en la barra de estado y se reintenta en el siguiente sondeo.
- **Un archivo JSON por nota**: una corrupción afecta a una sola nota. Las notas ilegibles se reportan, no tumban la app.
- **Papelera**: borrar mueve la nota a `papelera/`, desde donde se puede restaurar.
- **Seguridad**: los ids se validan como uuid hex, lo que impide rutas como `../../`.
- **Orden**: primero las fijadas y después por última modificación. El título es la primera línea no vacía.
- **Separación lógica / vista**: `almacen.py` y `autoguardado.py` no importan Tkinter.

## Arquitectura

```
notas/
├── almacen.py       # Nota, Almacen (CRUD, papelera), escribir_atomico
├── autoguardado.py  # Autoguardado (debounce + plazo máximo, reloj inyectable)
└── gui.py           # AppNotas (lista + editor + sondeo con after) y main()
```

## Instalación y uso

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m notas
```

Las notas se guardan en `~/.local/share/bloc-notas-py100/`.

## Tests

```bash
pytest
```

El test de humo de la GUI escribe en una nota, avanza el reloj falso y comprueba que se guardó sola y también al cerrar. Si no hay `DISPLAY` se omite (en un servidor: `xvfb-run pytest`).

## Limitaciones

- No hay sincronización entre dispositivos ni bloqueo si se abre la app dos veces: gana el último guardado.
- La búsqueda es lineal sobre todos los archivos. Sirve para cientos de notas; para miles convendría SQLite con FTS5.
- Es texto plano, sin vista previa de Markdown.
