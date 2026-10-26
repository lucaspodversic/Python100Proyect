"""cripto: consulta precios en la API pública de CoinGecko y avisa variaciones."""
# API pública: cliente de CoinGecko, reglas de alerta e historial.
from .api import ApiCoinGecko, Cotizacion
from .alertas import Alerta, ReglaVariacion, evaluar
from .historial import Historial

__all__ = ["ApiCoinGecko", "Cotizacion", "Alerta", "ReglaVariacion", "evaluar", "Historial"]
