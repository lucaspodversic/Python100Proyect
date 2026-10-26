"""Segmentación de clientes con RFM y K-Means."""

# Flujo: transacciones → calcular_rfm (una fila por cliente) → Segmentador (K-Means + nombres).
from .datos import generar_transacciones
from .rfm import calcular_rfm
from .clustering import Segmentador, elegir_k

__all__ = ["generar_transacciones", "calcular_rfm", "Segmentador", "elegir_k"]
