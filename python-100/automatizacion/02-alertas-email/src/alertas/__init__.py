"""Sistema de alertas por email ante cambios en archivos críticos."""

# API pública del paquete: el vigilante (detección) y los notificadores (canal de salida)
# están desacoplados; cualquier objeto con ``enviar(asunto, cuerpo, destinatarios)`` sirve.
from .notificador import FakeNotificador, Notificador, SMTPConfig, SMTPNotificador
from .vigilante import Cambio, Instantanea, Vigilante, comparar, tomar_instantanea

__all__ = [
    "Cambio", "Instantanea", "Vigilante", "comparar", "tomar_instantanea",
    "Notificador", "SMTPNotificador", "SMTPConfig", "FakeNotificador",
]
