"""Proveedores de precios detrás de una interfaz.

``AmadeusProveedor`` usa la API oficial *Amadeus Self-Service* (Flight Offers
Search v2), que tiene entorno de pruebas gratuito. Se autentica con OAuth2
``client_credentials`` y cachea el token hasta que vence.

El transporte HTTP es una función inyectable, así los tests no usan red.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from .modelos import Cotizacion, Seguimiento

# (método, url, headers, cuerpo) -> JSON decodificado
# Abstraer el HTTP en una función permite probar parseo, URL y caché de token sin red.
Transporte = Callable[[str, str, dict[str, str], bytes | None], Any]


def transporte_urllib(metodo: str, url: str, headers: dict[str, str], cuerpo: bytes | None) -> Any:  # pragma: no cover
    """Transporte real basado en urllib."""
    req = urllib.request.Request(url, data=cuerpo, headers=headers, method=metodo)
    with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310
        return json.loads(r.read().decode())


class ProveedorVuelos(Protocol):
    def buscar(self, s: Seguimiento) -> list[Cotizacion]: ...


@dataclass
class AmadeusProveedor:
    """Cliente mínimo de Amadeus. ``base`` = entorno de test por defecto."""

    client_id: str
    client_secret: str
    # Entorno de pruebas gratuito; para producción se pasa base="https://api.amadeus.com".
    base: str = "https://test.api.amadeus.com"
    transporte: Transporte = transporte_urllib
    reloj: Callable[[], float] = time.time
    moneda: str = "USD"
    # repr=False: el token no aparece al imprimir el objeto ni en logs.
    _token: str | None = field(default=None, repr=False)
    _vence: float = 0.0

    def _obtener_token(self) -> str:
        # Renovamos 60 s antes del vencimiento para evitar carreras.
        if self._token and self.reloj() < self._vence - 60:
            return self._token
        # OAuth2 client_credentials: el token se pide con form-urlencoded, no JSON.
        cuerpo = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": self.client_id,
                                         "client_secret": self.client_secret}).encode()
        r = self.transporte("POST", f"{self.base}/v1/security/oauth2/token",
                            {"Content-Type": "application/x-www-form-urlencoded"}, cuerpo)
        self._token = r["access_token"]
        # Amadeus devuelve expires_in=1799 s (~30 min); se usa como valor por defecto si falta.
        self._vence = self.reloj() + float(r.get("expires_in", 1799))
        return self._token

    def buscar(self, s: Seguimiento) -> list[Cotizacion]:
        q = urllib.parse.urlencode({"originLocationCode": s.origen, "destinationLocationCode": s.destino,
                                    "departureDate": s.fecha, "adults": s.adultos, "currencyCode": self.moneda,
                                    # max=20 ofertas: suficiente para encontrar la más barata sin respuestas enormes.
                                    "max": 20})
        r = self.transporte("GET", f"{self.base}/v2/shopping/flight-offers?{q}",
                            {"Authorization": f"Bearer {self._obtener_token()}"}, None)
        cotizaciones = []
        for oferta in r.get("data", []):
            # Primer tramo del itinerario de ida: identifica aerolínea, número de vuelo y salida.
            seg = oferta["itineraries"][0]["segments"][0]
            cotizaciones.append(Cotizacion(
                # grandTotal (con tasas) viene como string decimal: se convierte a float.
                precio=float(oferta["price"]["grandTotal"]), moneda=oferta["price"]["currency"],
                aerolinea=seg["carrierCode"], vuelo=f"{seg['carrierCode']}{seg['number']}",
                salida=seg["departure"]["at"]))
        return cotizaciones


@dataclass
class FakeProveedor:
    """Devuelve precios guionados: cada llamada consume la siguiente lista."""

    guion: list[list[float]]
    llamadas: int = 0

    def buscar(self, s: Seguimiento) -> list[Cotizacion]:
        # Si se agota el guion se repite la última lista (no IndexError en vigilancias largas).
        precios = self.guion[min(self.llamadas, len(self.guion) - 1)]
        self.llamadas += 1
        # Vuelos falsos XX100, XX101... uno por precio de la lista.
        return [Cotizacion(p, "USD", "XX", f"XX{100 + i}", f"{s.fecha}T10:00:00") for i, p in enumerate(precios)]
