# 100 · Snake y Pong (pygame + lógica headless)

Dos clásicos jugables con **pygame**, construidos sobre una lógica de juego
pura y determinista que se testea sin pantalla, sin teclado y sin reloj.

## Qué demuestra

- **Separación lógica/presentación**: `snake.py` y `pong.py` no importan
  pygame; reciben entradas (dirección, `dt`) y devuelven eventos. La ventana
  solo traduce teclado → entradas y estado → píxeles.
- **Snake por ticks**: cola de giros (dos teclas rápidas no se pierden),
  prohibición de giro de 180°, perseguir la propia cola no es choque,
  crecimiento diferido, modo sin paredes (toro), victoria al llenar el tablero
  y comida elegida de las celdas libres con un RNG con semilla.
- **Pong continuo**: ángulo de salida según dónde pega la pelota en la paleta
  (±60°), aceleración del 5 % por golpe con tope, rebotes que reflejan la
  posición, colisión círculo-rectángulo, **subpasos anti-túnel** y una IA con
  zona muerta.
- **Bucles de juego correctos**: paso fijo para Snake (la velocidad lógica no
  depende de los FPS) y `dt` acotado para Pong.
- Tests de humo de la capa pygame con los drivers `dummy` de SDL.

## Arquitectura

```
juegos/
├── snake.py     # Dir, Evento, Snake(girar, tick, velocidad, colocar_comida)
├── pong.py      # Paleta, Pelota, Pong(actualizar, sacar, ganador), ia()
├── ventana.py   # dibujar_snake, dibujar_pong, correr_snake, correr_pong, main (pygame perezoso)
└── __main__.py  # python -m juegos snake|pong
```

## Instalación y uso

```bash
pip install -e ".[juego]"            # instala pygame
python -m juegos snake               # flechas/WASD, P pausa, R reinicia, Esc sale
python -m juegos snake --sin-paredes --semilla 7
python -m juegos pong                # W/S contra la IA
python -m juegos pong --dos-jugadores  # W/S vs ↑/↓
```

## Tests

```bash
pip install -e ".[dev,juego]" && python -m pytest
```

- `test_snake.py`: posiciones exactas tick a tick sobre el tablero de 20x15
  (la cabeza arranca en (10, 7), la pared derecha se alcanza en el tick 10,
  etc.), cola de giros, choques, victoria en un tablero de 5x3.
- `test_pong.py`: rebote en techo, golpe centrado (sale recto ×1.05), golpe en
  el borde (tan 60°), anti-túnel a 900 px/s con `dt = 0.1`, puntos, fin de
  partida y una partida completa IA contra IA simulada a 60 FPS.
- `test_ventana.py`: dibuja en superficies en memoria y comprueba píxeles;
  corre unos cuadros de cada bucle con `SDL_VIDEODRIVER=dummy`. Se saltean si
  pygame no está instalado.

## Limitaciones

- Sin sonido, menús ni récords persistentes (se priorizó la lógica testeable).
- La IA de Pong no predice rebotes: solo sigue la altura de la pelota.
- Pong a dos jugadores es solo local (mismo teclado), sin red.
- El ganador por llenar el tablero en Snake es prácticamente inalcanzable en
  20x15 a velocidad máxima; está para completar las reglas.
