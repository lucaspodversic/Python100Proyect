"""habitos: registrá hábitos diarios y mirá rachas y estadísticas."""
# API pública: modelo, estadísticas y persistencia.
from .modelo import Habito, Estadisticas, estadisticas
from .almacen import Almacen

__all__ = ["Habito", "Estadisticas", "estadisticas", "Almacen"]
