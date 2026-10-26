"""Predictor de precios de vivienda (scikit-learn)."""

# datos = generador sintético con fórmula conocida; modelo = pipeline sklearn + persistencia.
from .datos import BARRIOS, COLUMNAS, generar_dataset
from .modelo import Predictor, comparar_modelos

__all__ = ["BARRIOS", "COLUMNAS", "generar_dataset", "Predictor", "comparar_modelos"]
