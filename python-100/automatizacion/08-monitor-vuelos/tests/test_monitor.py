"""Tests offline: proveedor/transporte falsos, SQLite en memoria, reloj controlado."""

from __future__ import annotations

import itertools
import urllib.parse
from typing import Any

import pytest

from monitor_vuelos import (AmadeusProveedor, Cotizacion, FakeNotificador, FakeProveedor, Historial,
                            Monitor, Seguimiento, WebhookNotificador, evaluar_alerta)
from monitor_vuelos.cli import main

# Seguimiento base: alerta si precio <= 900 o si cae 10% respecto del mínimo previo.
S = Seguimiento("EZE", "MAD", "2025-03-10", umbral=900, caida_pct=10)


def cot(p: float) -> Cotizacion:
    return Cotizacion(p, "USD", "IB", "IB6844", "2025-03-10T23:55:00")


def test_reglas_de_alerta() -> None:
    # 950 > 900 y sin historial → nada. 900 → umbral inclusivo.
    assert evaluar_alerta(S, cot(950), None, None) is None
    assert "umbral" in (evaluar_alerta(S, cot(900), None, None) or "")
    # 1020 vs mínimo 1200: 1 − 1020/1200 = 0.15 → 15.0% (>= 10%, alerta).
    assert "bajó 15.0%" in (evaluar_alerta(S, cot(1020), 1200, None) or "")
    # 1 − 1100/1200 = 0.0833 → 8.3% < 10%, no alcanza.
    assert evaluar_alerta(S, cot(1100), 1200, None) is None  # sólo 8.3%
    # Anti-spam: no repetir si no mejora la última alerta.
    assert evaluar_alerta(S, cot(880), None, 880) is None
    assert evaluar_alerta(S, cot(870), None, 880) is not None


def test_monitor_completo_con_historial() -> None:
    # Reloj que avanza 60 s por consulta: timestamps distintos y crecientes en el historial.
    reloj = itertools.count(1000, 60)
    fake = FakeNotificador()
    # Traza esperada de mínimos por revisión:
    #   1200 → sin previo, > 900 → nada
    #   1250 → mínimo previo 1200, subió → nada
    #   1050 → 1200 × 0.9 = 1080 ≥ 1050 → alerta por caída del 12.5%
    #   880  → ≤ 900 y < 1050 (última alerta) → alerta por umbral
    #   880  → igual a la última alerta → anti-spam, nada
    #   850  → < 880 → alerta por umbral
    prov = FakeProveedor([[1200, 1300], [1250], [1050], [880], [880], [850]])
    m = Monitor(prov, fake, Historial(), reloj=lambda: float(next(reloj)))
    esperas: list[float] = []
    alertas = m.vigilar([S], intervalo=3600, veces=6, dormir=esperas.append)
    assert [a.cotizacion.precio for a in alertas] == [1050, 880, 850]
    assert "bajó 12.5%" in fake.mensajes[0] and "umbral" in fake.mensajes[1]
    assert [p for _, p in m.historial.serie(S.clave)] == [1200, 1250, 1050, 880, 880, 850]
    # 6 revisiones → 5 esperas (no se duerme tras la última).
    assert len(esperas) == 5


def test_sin_cotizaciones_no_falla() -> None:
    # Caso borde: el proveedor no devolvió ofertas → se saltea sin romper min() sobre vacío.
    m = Monitor(FakeProveedor([[]]), FakeNotificador(), Historial())
    assert m.revisar([S]) == []


class TransporteFalso:
    """Imita las respuestas de Amadeus (token + flight-offers)."""

    def __init__(self) -> None:
        self.llamadas: list[tuple[str, str, dict[str, str], bytes | None]] = []

    def __call__(self, metodo: str, url: str, headers: dict[str, str], cuerpo: bytes | None) -> Any:
        self.llamadas.append((metodo, url, headers, cuerpo))
        # El token incluye el número de llamada ("tok1", "tok3"...) para distinguir renovaciones.
        if url.endswith("/v1/security/oauth2/token"):
            return {"access_token": f"tok{len(self.llamadas)}", "expires_in": 1799}
        return {"data": [
            # Dos ofertas con la estructura real de Flight Offers Search v2 (recortada).
            {"price": {"grandTotal": "1023.45", "currency": "USD"},
             "itineraries": [{"segments": [{"carrierCode": "IB", "number": "6844", "departure": {"at": "2025-03-10T23:55:00"}}]}]},
            {"price": {"grandTotal": "987.10", "currency": "USD"},
             "itineraries": [{"segments": [{"carrierCode": "AR", "number": "1132", "departure": {"at": "2025-03-10T13:30:00"}}]}]},
        ]}


def test_amadeus_parseo_y_cache_de_token() -> None:
    t = TransporteFalso()
    ahora = [0.0]
    prov = AmadeusProveedor("id", "secreto", transporte=t, reloj=lambda: ahora[0])
    cots = prov.buscar(S)
    assert [(c.vuelo, c.precio) for c in cots] == [("IB6844", 1023.45), ("AR1132", 987.10)]
    # llamadas[0] fue el POST del token; llamadas[1] la búsqueda.
    metodo, url, headers, _ = t.llamadas[1]
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    assert q["originLocationCode"] == ["EZE"] and q["departureDate"] == ["2025-03-10"]
    assert headers["Authorization"] == "Bearer tok1"
    prov.buscar(S)  # token aún válido: no se pide otro
    assert sum(u.endswith("token") for _, u, _, _ in t.llamadas) == 1
    # El token vence en 0 + 1799; con el margen de 60 s se renueva desde 1739. En 1800 hay que pedir otro.
    ahora[0] = 1800  # venció
    prov.buscar(S)
    assert sum(u.endswith("token") for _, u, _, _ in t.llamadas) == 2
    assert b"grant_type=client_credentials" in (t.llamadas[0][3] or b"")


def test_webhook_formato() -> None:
    enviados: list[tuple[str, dict[str, str]]] = []
    WebhookNotificador("https://hooks.ejemplo.invalid/x", enviar=lambda u, c: enviados.append((u, c))).notificar("hola")
    assert enviados == [("https://hooks.ejemplo.invalid/x", {"text": "hola"})]


# Guion demo: mínimos 1100, 1050, 880 (sin --caida) → sólo 880 ≤ 900 → "1 alerta(s)".
def test_cli_demo(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["eze", "mad", "2025-03-10", "--umbral", "900", "--demo", "--veces", "3", "--historial", ":memory:"]) == 0
    out = capsys.readouterr().out
    assert "EZE→MAD" in out and "1 alerta(s)" in out
