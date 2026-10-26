"""propinas: calcula propina y divide la cuenta sin errores de redondeo."""
# API pública: datos de la cuenta, resultado y funciones de cálculo.
from .calculo import Cuenta, Resultado, calcular, repartir

__all__ = ["Cuenta", "Resultado", "calcular", "repartir"]
