"""monitor_web: detecta cambios en páginas web y avisa con un diff legible."""
# Se reexporta la API pública para poder hacer `from monitor_web import Monitor`.
from .extraccion import extraer_texto, huella
from .monitor import Cambio, Monitor, Objetivo
from .notificar import NotificadorConsola, NotificadorWebhook

# __all__ define qué exporta `from monitor_web import *` y documenta la superficie pública.
__all__ = ["extraer_texto", "huella", "Cambio", "Monitor", "Objetivo", "NotificadorConsola", "NotificadorWebhook"]
