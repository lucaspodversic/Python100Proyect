# 55 · Juego 2048 en consola

El clásico 2048 jugable en la terminal con W/A/S/D.

## Qué demuestra
- **Lógica pura** separada de la interfaz: todo se reduce a `mover_fila` (izquierda);
  las demás direcciones se logran invirtiendo o trasponiendo la matriz.
- Regla correcta de fusión única por jugada (`[2,2,2,2] → [4,4,0,0]`).
- Aleatoriedad inyectable (`random.Random(semilla)`) → tests deterministas.
- Entrada/salida inyectables en la consola para testear el bucle.

## Arquitectura
```
juego2048/
  logica.py   # mover_fila, mover_tablero, Juego
  consola.py  # dibujar, jugar (bucle)
```

## Instalación y uso
```bash
pip install -e ".[dev]"
python -m juego2048
```
Escribí `w`, `a`, `s` o `d` y Enter. `q` sale.

## Tests
```bash
pytest
```

## Limitaciones
- Lee una tecla por línea (Enter); no usa `curses` para mantener compatibilidad con Windows.
