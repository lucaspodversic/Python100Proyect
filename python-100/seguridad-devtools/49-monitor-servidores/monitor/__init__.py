"""monitor: vigila CPU, memoria y disco y alerta por Slack/Discord."""
# API pública: lectura de métricas, reglas de alerta y notificadores.
from .metricas import Metricas, ProveedorLinux
from .reglas import Alerta, EvaluadorAlertas, Umbrales
from .notificadores import NotificadorDiscord, NotificadorSlack, TransporteHTTP

__all__ = ["Metricas", "ProveedorLinux", "Alerta", "EvaluadorAlertas", "Umbrales",
           "NotificadorDiscord", "NotificadorSlack", "TransporteHTTP"]
