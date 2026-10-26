"""Tests de la API del acortador (redirección, estadísticas, vencimiento)."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from acortador.app import crear_app


# Objeto invocable: crear_app lo llama como función para saber "la hora".
class RelojFalso:
    """Reloj controlable para simular el paso del tiempo."""
    def __init__(self):
        # Fecha fija: así las claves de "por_dia" del test son predecibles.
        self.t = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)

    def __call__(self):
        return self.t


@pytest.fixture()
def ctx():
    reloj = RelojFalso()
    # follow_redirects=False para poder inspeccionar el 307 y su Location.
    return TestClient(crear_app(":memory:", reloj=reloj), follow_redirects=False), reloj


# La redirección conserva ruta y query string completos.
def test_crear_y_redirigir(ctx):
    c, _ = ctx
    r = c.post("/api/enlaces", json={"url": "https://example.com/una/ruta/larga?x=1"})
    assert r.status_code == 201
    d = r.json()
    assert d["corto"].endswith("/" + d["codigo"])
    red = c.get("/" + d["codigo"])
    assert red.status_code == 307 and red.headers["location"] == "https://example.com/una/ruta/larga?x=1"


# Clics: 2 el 1/1 (uno de twitter, uno directo) y 1 el 2/1 (twitter) =>
# total 3, por día {1/1: 2, 2/1: 1}, por referer {twitter.com: 2, directo: 1}.
# Las dos URLs de twitter son distintas pero cuentan juntas (solo el host).
def test_estadisticas_por_dia_y_referer(ctx):
    c, reloj = ctx
    cod = c.post("/api/enlaces", json={"url": "https://example.com"}).json()["codigo"]
    c.get("/" + cod, headers={"referer": "https://twitter.com/post/1"})
    c.get("/" + cod)
    reloj.t += timedelta(days=1)
    c.get("/" + cod, headers={"referer": "https://twitter.com/otro"})
    s = c.get(f"/api/enlaces/{cod}").json()
    assert s["clics"] == 3
    assert s["por_dia"] == {"2026-01-01": 2, "2026-01-02": 1}
    assert s["por_referer"] == {"twitter.com": 2, "directo": 1}


# "promo" se acepta; repetirlo da 409; "docs" está reservado (422).
def test_alias_personalizado_y_duplicado(ctx):
    c, _ = ctx
    assert c.post("/api/enlaces", json={"url": "https://a.com", "alias": "promo"}).json()["codigo"] == "promo"
    assert c.post("/api/enlaces", json={"url": "https://b.com", "alias": "promo"}).status_code == 409
    assert c.post("/api/enlaces", json={"url": "https://b.com", "alias": "docs"}).status_code == 422


# javascript: podría ejecutar código al hacer clic en el enlace corto.
def test_url_peligrosa(ctx):
    c, _ = ctx
    assert c.post("/api/enlaces", json={"url": "javascript:alert(1)"}).status_code == 422


# Válido por 2 días: a los 0 días redirige, a los 3 días da 410.
def test_vencimiento(ctx):
    c, reloj = ctx
    cod = c.post("/api/enlaces", json={"url": "https://a.com", "dias_validez": 2}).json()["codigo"]
    assert c.get("/" + cod).status_code == 307
    reloj.t += timedelta(days=3)
    assert c.get("/" + cod).status_code == 410


# Token incorrecto 403; correcto 204; después el código ya no existe (404).
def test_borrado_con_token(ctx):
    c, _ = ctx
    d = c.post("/api/enlaces", json={"url": "https://a.com"}).json()
    assert c.delete(f"/api/enlaces/{d['codigo']}", headers={"X-Token-Borrado": "x"}).status_code == 403
    assert c.delete(f"/api/enlaces/{d['codigo']}", headers={"X-Token-Borrado": d["token_borrado"]}).status_code == 204
    assert c.get("/" + d["codigo"]).status_code == 404


def test_inexistente(ctx):
    c, _ = ctx
    assert c.get("/noexiste").status_code == 404
    assert c.get("/health").json() == {"ok": True}
