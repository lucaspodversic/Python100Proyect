"""Limpiador de bandeja de entrada basado en reglas (Gmail API)."""

# modelos = datos y reglas puras; motor = evaluación y aplicación; gmail = adaptador de la API
# real y un fake en memoria con la misma interfaz.
from .modelos import Accion, Condicion, Correo, Regla
from .motor import Motor, Reporte, cargar_reglas
from .gmail import ClienteCorreo, FakeCliente, GmailCliente

__all__ = ["Correo", "Condicion", "Accion", "Regla", "Motor", "Reporte", "cargar_reglas",
           "ClienteCorreo", "GmailCliente", "FakeCliente"]
