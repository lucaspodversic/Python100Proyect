"""Bot de postulación automática a ofertas de empleo — versión ética de demostración.

Corre SIEMPRE contra un sitio mock local (``sitio_mock``) que imita el flujo
de un portal de empleo: listado paginado -> detalle -> formulario. No incluye
URLs, selectores ni credenciales de portales reales.
"""

# Reglas puras (perfil) separadas del orquestador (bot): la decisión se testea sin red.
from .perfil import Decision, Oferta, Perfil, evaluar
from .bot import BotPostulaciones, Resultado

__all__ = ["Perfil", "Oferta", "Decision", "evaluar", "BotPostulaciones", "Resultado"]
