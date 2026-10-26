"""audiolibro: extrae texto de un PDF y lo convierte a voz (MP3)."""
# API pública: preparación del texto y conversión a audio.
from .texto import extraer_texto, limpiar_texto, trocear
from .convertidor import Convertidor, MotorGTTS, MotorVoz

__all__ = ["extraer_texto", "limpiar_texto", "trocear", "Convertidor", "MotorGTTS", "MotorVoz"]
