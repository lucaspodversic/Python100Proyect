"""escaner: escáner TCP connect() concurrente para auditar hosts PROPIOS."""
# API pública: estados, resultado, función de escaneo y parser de rangos.
from .nucleo import EstadoPuerto, ResultadoPuerto, escanear, parsear_puertos

__all__ = ["EstadoPuerto", "ResultadoPuerto", "escanear", "parsear_puertos"]
