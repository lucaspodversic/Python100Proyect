"""Cliente de Open-Meteo (https://open-meteo.com).

- Geocodificación: nombre de ciudad → coordenadas.
- Pronóstico (hasta 16 días) y archivo histórico diario.
Es una API abierta pensada para uso programático: no hace falta
scrapear sitios del clima. Uso no comercial gratuito (ver sus términos).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from urllib.parse import urlencode

from .cliente import ClienteEducado

# Endpoints oficiales; se pueden reemplazar en el constructor (los tests apuntan a 127.0.0.1).
GEO = "https://geocoding-api.open-meteo.com/v1/search"
PRONOSTICO = "https://api.open-meteo.com/v1/forecast"
HISTORICO = "https://archive-api.open-meteo.com/v1/archive"
# Variables diarias pedidas. El ORDEN importa: DiaClima se construye posicionalmente con ellas.
VARIABLES = ("temperature_2m_max", "temperature_2m_min", "precipitation_sum", "wind_speed_10m_max")


@dataclass(frozen=True)
class Lugar:
    """Resultado de la geocodificación."""

    nombre: str
    pais: str
    latitud: float
    longitud: float


@dataclass(frozen=True)
class DiaClima:
    """Datos de un día. Cualquier valor puede ser None: la API devuelve null si falta el dato."""

    fecha: date
    t_max: float | None        # °C
    t_min: float | None        # °C
    lluvia_mm: float | None    # precipitación total del día
    viento_max: float | None   # km/h (unidad por defecto de Open-Meteo)


class ApiOpenMeteo:
    """Envoltorio fino sobre las tres APIs de Open-Meteo."""

    def __init__(self, cliente: ClienteEducado | None = None, geo: str = GEO,
                 pronostico: str = PRONOSTICO, historico: str = HISTORICO) -> None:
        # 1 s entre pedidos al mismo host: muy por debajo de los límites de la API.
        self.cliente = cliente or ClienteEducado(intervalo=1.0)
        self.geo, self.url_pron, self.url_hist = geo, pronostico, historico

    def buscar_lugar(self, nombre: str, idioma: str = "es") -> Lugar:
        """Devuelve el primer resultado de la búsqueda; LookupError si no hay ninguno."""
        # urlencode escapa tildes y espacios ("Córdoba" → "C%C3%B3rdoba").
        d = self.cliente.get(f"{self.geo}?{urlencode({'name': nombre, 'count': 1, 'language': idioma})}").json()
        # Sin coincidencias la API omite "results" (no devuelve lista vacía): se cubren ambos casos.
        if not d.get("results"):
            raise LookupError(f"No se encontró «{nombre}»")
        r = d["results"][0]
        return Lugar(r["name"], r.get("country", ""), float(r["latitude"]), float(r["longitude"]))

    def _diario(self, url: str, lugar: Lugar, extra: dict) -> list[DiaClima]:
        """Pedido común a pronóstico e histórico: ambas APIs devuelven el mismo bloque "daily"."""
        # timezone=auto: los días se cortan a medianoche LOCAL del lugar, no en UTC.
        params = {"latitude": lugar.latitud, "longitude": lugar.longitud, "daily": ",".join(VARIABLES),
                  "timezone": "auto", **extra}
        d = self.cliente.get(f"{url}?{urlencode(params)}").json()
        # Open-Meteo informa errores de parámetros como {"error": true, "reason": "..."}.
        if d.get("error"):
            raise ValueError(d.get("reason", "Error de la API"))
        dia = d["daily"]
        # "daily" es columnar (una lista por variable); se transpone a una fila por día.
        return [DiaClima(date.fromisoformat(f), *(dia[v][i] for v in VARIABLES)) for i, f in enumerate(dia["time"])]

    def pronostico(self, lugar: Lugar, dias: int = 7) -> list[DiaClima]:
        """Pronóstico diario; la API admite 1-16 días (se valida antes de pedir)."""
        if not 1 <= dias <= 16:
            raise ValueError("El pronóstico admite entre 1 y 16 días")
        return self._diario(self.url_pron, lugar, {"forecast_days": dias})

    def historico(self, lugar: Lugar, desde: date, hasta: date) -> list[DiaClima]:
        """Datos observados entre dos fechas inclusive (archivo ERA5 de Open-Meteo)."""
        if desde > hasta:
            raise ValueError("'desde' debe ser anterior a 'hasta'")
        return self._diario(self.url_hist, lugar, {"start_date": desde.isoformat(), "end_date": hasta.isoformat()})
