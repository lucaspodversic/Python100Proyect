"""Predicción de duración de entregas."""

# datos = generador con fórmula conocida; modelo = GBR (estimado) + cuantiles p10/p90.
from .datos import COLUMNAS, generar_pedidos
from .modelo import PredictorEntregas, evaluar

__all__ = ["COLUMNAS", "generar_pedidos", "PredictorEntregas", "evaluar"]
