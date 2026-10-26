"""Monitor de precios de vuelos con alertas por umbral y por caída porcentual."""

# Capas: modelos (datos) → proveedores (de dónde salen los precios) → historial (SQLite)
# → monitor (reglas + orquestación) → notificadores (a dónde va la alerta).
from .modelos import Cotizacion, Seguimiento
from .proveedores import AmadeusProveedor, FakeProveedor, ProveedorVuelos
from .historial import Historial
from .monitor import Alerta, Monitor, evaluar_alerta
from .notificadores import ConsolaNotificador, FakeNotificador, WebhookNotificador

__all__ = ["Cotizacion", "Seguimiento", "ProveedorVuelos", "AmadeusProveedor", "FakeProveedor",
           "Historial", "Monitor", "Alerta", "evaluar_alerta",
           "ConsolaNotificador", "FakeNotificador", "WebhookNotificador"]
