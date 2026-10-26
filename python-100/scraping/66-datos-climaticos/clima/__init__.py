"""clima: datos meteorológicos desde la API pública Open-Meteo (sin clave)."""
# API pública del paquete: modelos, cliente de la API y funciones de análisis.
from .api import ApiOpenMeteo, Lugar, DiaClima
from .analisis import Estadisticas, estadisticas, grafico_ascii, guardar_csv

__all__ = ["ApiOpenMeteo", "Lugar", "DiaClima", "Estadisticas", "estadisticas", "grafico_ascii", "guardar_csv"]
