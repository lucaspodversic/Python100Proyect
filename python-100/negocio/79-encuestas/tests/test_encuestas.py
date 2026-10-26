"""Tests de encuestas: validación, códigos de un solo uso, agregación, CSV y PNG."""
from __future__ import annotations

import csv
import io
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import graficos
from app.main import crear_app

AHORA = datetime(2026, 7, 1, 12)


@pytest.fixture()
def c(tmp_path):
    return TestClient(crear_app(f"sqlite:///{tmp_path / 'e.db'}", reloj=lambda: AHORA))


@pytest.fixture()
def h(c):
    c.post("/auth/registro", json={"email": "ana@x.com", "nombre": "Ana", "password": "secreta123"})
    return {"Authorization": "Bearer " + c.post("/auth/login", json={"email": "ana@x.com", "password": "secreta123"}).json()["token"]}


@pytest.fixture()
def enc(c, h):
    r = c.post("/encuestas", headers=h, json={"titulo": "Satisfacción", "preguntas": [
        {"texto": "¿Lenguaje favorito?", "tipo": "unica", "opciones": ["Python", "Go", "Rust"]},
        {"texto": "¿Qué usás?", "tipo": "multiple", "opciones": ["Linux", "Mac", "Windows"]},
        {"texto": "Puntaje", "tipo": "escala"},
        {"texto": "Comentarios", "tipo": "texto", "obligatoria": False}]})
    assert r.status_code == 201, r.text
    return r.json()


def resp(c, enc, u, m, e, t=None, codigo=None):
    p = enc["preguntas"]
    valores = {str(p[0]): u, str(p[1]): m, str(p[2]): e}
    if t is not None:
        valores[str(p[3])] = t
    return c.post(f"/e/{enc['slug']}/responder", json={"valores": valores, "codigo": codigo})


def test_definicion_invalida(c, h):
    r = c.post("/encuestas", headers=h, json={"titulo": "Mala", "preguntas": [{"texto": "x", "tipo": "unica", "opciones": ["a"]}]})
    assert r.status_code == 400
    r = c.post("/encuestas", headers=h, json={"titulo": "Mala", "preguntas": [{"texto": "x", "tipo": "escala", "opciones": ["a", "b"]}]})
    assert r.status_code == 400


def test_validacion_respuestas(c, enc):
    assert resp(c, enc, "Java", ["Linux"], 3).status_code == 400          # opción inexistente
    assert resp(c, enc, "Go", [], 3).status_code == 400                   # obligatoria vacía
    assert resp(c, enc, "Go", ["Linux"], 6).status_code == 400            # fuera de escala
    assert resp(c, enc, "Go", ["Linux"], True).status_code == 400         # bool no es entero válido
    assert resp(c, enc, "Go", ["Linux", "Linux"], 4).status_code == 201   # duplicados se normalizan
    r = c.post(f"/e/{enc['slug']}/responder", json={"valores": {"999": "x"}})
    assert r.status_code == 400


def test_resultados_csv_y_grafico(c, h, enc):
    resp(c, enc, "Python", ["Linux", "Mac"], 5, "=HYPERLINK(\"http://malo\")")
    resp(c, enc, "Python", ["Linux"], 4)
    resp(c, enc, "Rust", ["Windows"], 3, "Muy bueno")
    res = c.get(f"/encuestas/{enc['id']}/resultados", headers=h).json()
    assert res["total"] == 3
    unica, multiple, escala, texto = res["preguntas"]
    assert unica["conteo"] == {"Python": 2, "Go": 0, "Rust": 1}
    assert multiple["conteo"] == {"Linux": 2, "Mac": 1, "Windows": 1}
    assert escala["promedio"] == 4.0 and escala["conteo"]["5"] == 1
    assert texto["respondidas"] == 2
    filas = list(csv.reader(io.StringIO(c.get(f"/encuestas/{enc['id']}/resultados.csv", headers=h).text)))
    assert filas[0][0] == "¿Lenguaje favorito?" and filas[1][1] == "Linux; Mac"
    assert filas[1][3].startswith("'=")  # fórmula neutralizada
    png = c.get(f"/encuestas/{enc['id']}/preguntas/{enc['preguntas'][2]}/grafico.png", headers=h)
    assert png.headers["content-type"] == "image/png" and png.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert c.get(f"/encuestas/{enc['id']}/preguntas/{enc['preguntas'][3]}/grafico.png", headers=h).status_code == 400


def test_codigos_un_solo_uso_y_cierre(c, h, enc):
    codigos = c.post(f"/encuestas/{enc['id']}/codigos", headers=h, json={"cantidad": 2}).json()["codigos"]
    assert len(set(codigos)) == 2
    assert resp(c, enc, "Go", ["Mac"], 2).status_code == 403                       # falta código
    assert resp(c, enc, "Go", ["Mac"], 2, codigo="NOEXISTE").status_code == 403
    assert resp(c, enc, "Go", ["Mac"], 2, codigo=codigos[0].lower()).status_code == 201  # insensible a mayúsculas
    assert resp(c, enc, "Go", ["Mac"], 2, codigo=codigos[0]).status_code == 403    # ya usado
    c.post(f"/encuestas/{enc['id']}/cerrar", headers=h)
    assert resp(c, enc, "Go", ["Mac"], 2, codigo=codigos[1]).status_code == 409


def test_privacidad_de_resultados(c, h, enc):
    c.post("/auth/registro", json={"email": "bob@x.com", "nombre": "Bob", "password": "secreta123"})
    hb = {"Authorization": "Bearer " + c.post("/auth/login", json={"email": "bob@x.com", "password": "secreta123"}).json()["token"]}
    assert c.get(f"/encuestas/{enc['id']}/resultados", headers=hb).status_code == 404
    publica = c.get(f"/e/{enc['slug']}").json()
    assert publica["titulo"] == "Satisfacción" and "total" not in publica


def test_grafico_unidad():
    png = graficos.grafico_barras("Prueba", {"a": 1, "b": 3}, promedio=2.5)
    assert png.startswith(b"\x89PNG") and len(png) > 1000
