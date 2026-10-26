"""Análisis de sentimiento de feedback de clientes en español."""

# texto = normalización (negación, tildes); corpus = datos de entrenamiento y evaluación;
# modelo = TF-IDF + regresión logística.
from .texto import normalizar
from .corpus import cargar_reseñas_reales, generar_corpus
from .modelo import ClasificadorSentimiento

__all__ = ["normalizar", "generar_corpus", "cargar_reseñas_reales", "ClasificadorSentimiento"]
