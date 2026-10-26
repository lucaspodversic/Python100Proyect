"""organizador: mueve automáticamente los archivos de Descargas a carpetas."""
# API pública: reglas de clasificación y el motor que mueve archivos.
from .reglas import Regla, REGLAS_POR_DEFECTO, destino_para
from .motor import Organizador, Movimiento

__all__ = ["Regla", "REGLAS_POR_DEFECTO", "destino_para", "Organizador", "Movimiento"]
