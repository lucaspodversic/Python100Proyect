"""Clasificación de enfermedades en hojas con una CNN."""

# datos = imágenes (sintéticas o carpetas); modelo = arquitectura; entrenamiento = bucle, métricas, persistencia.
from .datos import CLASES_SINTETICAS, DatasetCarpetas, generar_hojas
from .modelo import RedHojas
from .entrenamiento import Clasificador

__all__ = ["CLASES_SINTETICAS", "generar_hojas", "DatasetCarpetas", "RedHojas", "Clasificador"]
