# 87 · Reloj, cronómetro y temporizador con alarma (Tkinter)

Aplicación con cuatro pestañas:

- **Reloj**.
- **Cronómetro**, con vueltas.
- **Temporizador**, con barra de progreso y aviso al terminar.
- **Alarmas**, a una hora del día, con días de la semana opcionales y posposición.

## Qué demuestra

- **Relojes inyectables**: toda la lógica (`tiempo.py`) recibe el reloj como parámetro. Los tests usan relojes falsos y se ejecutan al instante, sin `sleep`.
- **Reloj monotónico vs. hora de pared**:
  - El cronómetro y el temporizador usan `time.monotonic`, que no salta si se cambia la hora del sistema o el horario de verano.
  - Las alarmas usan `datetime`, porque se refieren a la hora de la pared.
- **Avisos que no se repiten**:
  - El temporizador avisa exactamente una vez.
  - La alarma suena una vez por día, con una tolerancia de 60 s (por ejemplo, si el equipo estuvo suspendido un momento). La posposición (*snooze*) suena al vencer.
- **Pausa sin deriva**: el tiempo se acumula por tramos (inicio → pausa), no sumando *ticks*. El intervalo del `after` no afecta a la precisión.
- **Entrada flexible**: `90`, `05:00`, `1:02:03` o `1h 30m 15s`, con validación.
- **Separación lógica / vista**: un único bucle `after` de 50 ms llama a `actualizar()`, que también se puede invocar directamente en los tests. El aviso (`messagebox` + `bell`) es inyectable para no bloquear los tests.

## Arquitectura

```
reloj/
├── tiempo.py  # formatear, parsear_duracion, Cronometro, Temporizador, Alarma
└── gui.py     # AppReloj (Notebook con 4 pestañas) y main()
```

## Instalación y uso

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m reloj
```

## Tests

```bash
pytest
```

El test de humo de la GUI usa relojes falsos para hacer correr un temporizador y disparar una alarma. Si no hay `DISPLAY` se omite (en un servidor: `xvfb-run pytest`).

## Limitaciones

- Las alarmas viven en memoria: se pierden al cerrar la app y solo suenan si está abierta.
- El sonido es el `bell()` del sistema. Para reproducir un archivo de audio se podría reutilizar el motor del proyecto 82.
- La GUI no permite elegir días para las alarmas (la lógica sí lo admite).
