"""Detección de fraude con clases desbalanceadas."""

# datos = generador sintético; umbral = criterios de negocio; modelo = pipelines, entrenamiento y comparación.
from .datos import ATRIBUTOS, generar_transacciones
from .umbral import Costos, costo_total, umbral_minimo_costo, umbral_para_recall
from .modelo import DetectorFraude, comparar

__all__ = ["ATRIBUTOS", "generar_transacciones", "Costos", "costo_total", "umbral_minimo_costo",
           "umbral_para_recall", "DetectorFraude", "comparar"]
