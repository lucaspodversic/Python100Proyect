"""Cliente de la API oficial de CoinGecko (endpoint `/simple/price`).

Se usa la API en lugar de scrapear la web: es estable, documentada y
pensada para esto. El plan gratuito tiene límite de pedidos por minuto,
por eso el cliente aplica un intervalo mínimo entre llamadas.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlencode

from .cliente import ClienteEducado

# Endpoint público v3; en los tests se reemplaza por un servidor en 127.0.0.1.
URL_BASE = "https://api.coingecko.com/api/v3"


@dataclass(frozen=True)
class Cotizacion:
    """Precio de una moneda en una divisa en un momento dado."""
    moneda: str          # id de CoinGecko, p. ej. "bitcoin"
    precio: float
    divisa: str          # "usd", "eur", ...
    cambio_24h: float | None
    momento: datetime


class ApiCoinGecko:
    """Consulta /simple/price a través del cliente educado."""
    def __init__(self, cliente: ClienteEducado | None = None, url_base: str = URL_BASE,
                 clave_api: str | None = None) -> None:
        # 6 s entre pedidos ≈ 10/min, por debajo del límite del plan gratuito
        self.cliente = cliente or ClienteEducado(intervalo=6.0)
        # Sin "/" final para armar las URLs sin barras dobles.
        self.url_base = url_base.rstrip("/")
        # Clave opcional del plan "demo" gratuito de CoinGecko.
        self.clave_api = clave_api

    def precios(self, ids: list[str], divisa: str = "usd") -> list[Cotizacion]:
        """Cotización actual de varias monedas en una divisa (una sola llamada)."""
        # Caso borde: no se hace un pedido vacío.
        if not ids:
            raise ValueError("Indicá al menos una moneda")
        # Un único pedido para todas las monedas; se pide también el cambio de 24 h y la hora de actualización.
        q = urlencode({"ids": ",".join(ids), "vs_currencies": divisa, "include_24hr_change": "true",
                       "include_last_updated_at": "true"})
        cab = {"Accept": "application/json"}
        if self.clave_api:
            # Cabecera documentada por CoinGecko para la clave demo.
            cab["x-cg-demo-api-key"] = self.clave_api
        # Respuesta: {"bitcoin": {"usd": 60000, "usd_24h_change": 1.2, "last_updated_at": 1790000000}, ...}
        datos = self.cliente.get(f"{self.url_base}/simple/price?{q}", cab).json()
        res = []
        # Se recorre en el orden pedido para que la salida sea predecible.
        for m in ids:
            d = datos.get(m)
            if not d or divisa not in d:
                continue  # id inexistente: CoinGecko simplemente lo omite
            ts = d.get("last_updated_at")
            # Timestamp Unix → datetime con zona UTC; si falta, se usa la hora actual.
            momento = datetime.fromtimestamp(ts, timezone.utc) if ts else datetime.now(timezone.utc)
            res.append(Cotizacion(m, float(d[divisa]), divisa, d.get(f"{divisa}_24h_change"), momento))
        return res
