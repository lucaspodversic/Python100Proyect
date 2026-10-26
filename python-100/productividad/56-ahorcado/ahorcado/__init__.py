"""ahorcado: el juego del ahorcado con arte ASCII y lógica pura."""
# API pública: lógica de la partida y banco de palabras.
from .logica import Partida, Resultado, normalizar
from .palabras import PALABRAS

__all__ = ["Partida", "Resultado", "normalizar", "PALABRAS"]
