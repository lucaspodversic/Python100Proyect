"""juego2048: el clásico 2048 con la lógica separada de la interfaz."""
# API pública: sólo la lógica (la consola es un detalle de interfaz).
from .logica import Direccion, Juego, mover_fila, mover_tablero

__all__ = ["Direccion", "Juego", "mover_fila", "mover_tablero"]
