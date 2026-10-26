# 82 · Reproductor de música (Tkinter + pygame.mixer)

Reproductor de escritorio que carga una carpeta de música (mp3, ogg, wav, flac) y ofrece reproducir, pausar, siguiente/anterior, aleatorio, repetición (no / todas / una) y volumen.

## Qué demuestra

- **Audio detrás de una interfaz**:
  - El controlador solo conoce el protocolo `MotorAudio`.
  - `MotorPygame` usa `pygame.mixer.music` (streaming), y pygame se importa solo al crearlo.
  - `MotorFalso` registra las llamadas y simula el fin de pista, así que los tests no necesitan audio ni pygame.
- **Máquina de estados**: `detenido → reproduciendo ⇄ pausado`. El método `tick()`, llamado con `after()`, detecta el fin de pista y avanza respetando el modo de repetición.
- **Aleatorio reproducible**: usa un `random.Random` propio (sembrable), deja la pista actual primera y, al desactivarlo, se vuelve al orden original sin perder la pista.
- **Robustez**: los archivos corruptos o no soportados se saltan y se avisan, sin bucle infinito aunque estén todos rotos. Al quitar pistas se reajusta la posición actual.
- **Separación lógica / vista**: `lista.py` y `control.py` son puros. `gui.py` crea la ventana solo en `main()`.

## Arquitectura

```
reproductor/
├── audio.py    # MotorAudio (Protocol), MotorPygame, MotorFalso
├── lista.py    # ListaReproduccion, Repetir, escanear()
├── control.py  # Reproductor (estado + coordinación)
└── gui.py      # AppReproductor y main()
```

## Instalación y uso

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m reproductor ~/Música      # o abrir la carpeta desde el botón
```

Doble clic en una pista para reproducirla.

## Tests

```bash
pytest
```

Los tests de lista y controlador no necesitan pantalla ni audio. El test de humo de la GUI se omite si no hay `DISPLAY` (para correrlo en un servidor: `xvfb-run pytest`).

## Limitaciones

- `pygame.mixer.music` no informa la duración de los mp3, así que no hay barra de progreso ni búsqueda dentro de la pista.
- No lee etiquetas ID3: se muestra el nombre del archivo. Para leerlas se podría usar `mutagen`.
- El fin de pista se detecta con un sondeo cada 500 ms, no por evento.
