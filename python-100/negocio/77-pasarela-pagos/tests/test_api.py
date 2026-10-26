"""Tests de la API: idempotencia, reembolsos, webhooks firmados y concurrencia."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app import servicio, webhooks
from app.main import crear_app
from app.modelos import Usuario

AHORA = datetime(2026, 4, 1, 10, 0)
VISA = {"numero": "4242424242424242", "mes": 12, "anio": 2030}


class TransporteFalso:
    """Registra las entregas en memoria; puede simular un receptor caído."""

    def __init__(self) -> None:
        self.recibidos: list[tuple[str, dict, bytes]] = []
        self.estado = 200

    def __call__(self, url, cabeceras, cuerpo):
        if self.estado == 0:
            raise ConnectionError("sin red")
        self.recibidos.append((url, cabeceras, cuerpo))
        return self.estado


@pytest.fixture()
def transporte():
    return TransporteFalso()


@pytest.fixture()
def app(tmp_path, transporte):
    return crear_app(f"sqlite:///{tmp_path / 'p.db'}", transporte=transporte, reloj=lambda: AHORA)


@pytest.fixture()
def c(app):
    return TestClient(app)


def comercio(c, email="tienda@x.com"):
    c.post("/auth/registro", json={"email": email, "nombre": "Tienda", "password": "secreta123"})
    return {"Authorization": "Bearer " + c.post("/auth/login", json={"email": email, "password": "secreta123"}).json()["token"]}


def pagar(c, h, clave, monto=10_000, tarjeta=VISA):
    return c.post("/pagos", headers={**h, "Idempotency-Key": clave},
                  json={"monto_centavos": monto, "moneda": "ars", "tarjeta": tarjeta})


def test_pago_idempotente(c):
    h = comercio(c)
    r1 = pagar(c, h, "clave-0001")
    assert r1.status_code == 201 and r1.headers["Idempotent-Replayed"] == "false"
    r2 = pagar(c, h, "clave-0001")
    assert r2.status_code == 201 and r2.headers["Idempotent-Replayed"] == "true"
    assert r1.json() == r2.json()
    assert len(c.get("/pagos", headers=h).json()) == 1  # se cobró una sola vez
    # Misma clave con otro monto: error de uso.
    assert pagar(c, h, "clave-0001", monto=5).status_code == 422
    # Sin clave: rechazado por validación.
    assert c.post("/pagos", headers=h, json={"monto_centavos": 1, "moneda": "ARS", "tarjeta": VISA}).status_code == 422
    # La clave es por comercio: otro comercio puede usar la misma.
    assert pagar(c, comercio(c, "otra@x.com"), "clave-0001").status_code == 201


def test_rechazos_y_privacidad(c):
    h = comercio(c)
    r = pagar(c, h, "clave-rech", tarjeta={"numero": "4000000000000002", "mes": 1, "anio": 2030})
    assert r.status_code == 402 and r.json()["motivo_rechazo"] == "tarjeta_rechazada"
    assert "4000000000000002" not in json.dumps(r.json())  # nunca se devuelve el PAN
    pid = pagar(c, h, "clave-okok").json()["id"]
    assert c.get(f"/pagos/{pid}", headers=comercio(c, "otra@x.com")).status_code == 404
    assert c.post(f"/pagos/{r.json()['id']}/reembolsos", headers={**h, "Idempotency-Key": "re-000001"},
                  json={}).status_code == 409


def test_reembolsos_parciales(c):
    h = comercio(c)
    pid = pagar(c, h, "clave-0002", monto=10_000).json()["id"]

    def reemb(clave, monto=None):
        return c.post(f"/pagos/{pid}/reembolsos", headers={**h, "Idempotency-Key": clave},
                      json={} if monto is None else {"monto_centavos": monto})

    assert reemb("re-000001", 3_000).json()["estado_pago"] == "reembolsado_parcial"
    assert reemb("re-000001", 3_000).headers["Idempotent-Replayed"] == "true"  # no duplica
    assert reemb("re-000002", 8_000).status_code == 409  # supera lo disponible
    assert reemb("re-000003").json()["monto_centavos"] == 7_000  # sin monto = el resto
    pago = c.get(f"/pagos/{pid}", headers=h).json()
    assert pago["estado"] == "reembolsado" and pago["reembolsado_centavos"] == 10_000


def test_webhooks_firmados_y_reintentos(c, transporte):
    h = comercio(c)
    assert c.post("/eventos/despachar", headers=h).status_code == 409  # sin configurar
    secreto = c.post("/webhook", headers=h, json={"url": "https://tienda.example/hook"}).json()["secreto"]
    pagar(c, h, "clave-0003")
    transporte.estado = 0  # receptor caído
    assert c.post("/eventos/despachar", headers=h).json() == {"entregados": 0, "fallidos": 1}
    assert c.get("/eventos", headers=h).json()[0]["ultimo_error"] == "ConnectionError"
    transporte.estado = 200
    assert c.post("/eventos/despachar", headers=h).json() == {"entregados": 1, "fallidos": 0}
    url, cab, cuerpo = transporte.recibidos[-1]
    ahora_unix = int(AHORA.replace(tzinfo=timezone.utc).timestamp())
    # El receptor verifica la firma con su secreto.
    assert webhooks.verificar(secreto, cuerpo, cab["Firma-Pasarela"], ahora=ahora_unix)
    assert json.loads(cuerpo)["tipo"] == "pago.aprobado"
    ev = c.get("/eventos", headers=h).json()[0]
    assert ev["entregado"] and ev["intentos"] == 2
    # Ya entregado: no se reenvía.
    assert c.post("/eventos/despachar", headers=h).json() == {"entregados": 0, "fallidos": 0}


def test_reembolsos_concurrentes_no_exceden(app, c):
    h = comercio(c)
    pid = pagar(c, h, "clave-0004", monto=10_000).json()["id"]
    exitos, errores = [], []
    barrera = threading.Barrier(8)

    def intentar(i: int) -> None:
        barrera.wait()
        try:
            with app.state.fabrica.begin() as s:
                servicio.reembolsar(s, s.get(Usuario, 1), pid, 3_000, "", AHORA)
            exitos.append(i)
        except servicio.ErrorNegocio:
            errores.append(i)

    hilos = [threading.Thread(target=intentar, args=(i,)) for i in range(8)]
    for t in hilos:
        t.start()
    for t in hilos:
        t.join()
    # 10.000 / 3.000 -> solo 3 reembolsos caben.
    assert len(exitos) == 3 and len(errores) == 5
    assert c.get(f"/pagos/{pid}", headers=h).json()["reembolsado_centavos"] == 9_000
