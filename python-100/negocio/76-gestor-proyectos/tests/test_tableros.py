"""Tests del gestor de proyectos: permisos por tablero, orden y filtros."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.main import crear_app


@pytest.fixture()
def c(tmp_path):
    return TestClient(crear_app(f"sqlite:///{tmp_path / 'p.db'}", hoy=lambda: date(2026, 5, 10)))


def usuario(c, email):
    r = c.post("/auth/registro", json={"email": email, "nombre": email[:3], "password": "secreta123"})
    tok = c.post("/auth/login", json={"email": email, "password": "secreta123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}, r.json()["id"]


@pytest.fixture()
def tablero(c):
    """Tablero de Ana con las tres listas por defecto."""
    ana, _ = usuario(c, "ana@x.com")
    t = c.post("/tableros", headers=ana, json={"nombre": "Lanzamiento"}).json()
    return ana, t


def titulos(c, h, tid):
    return {l["nombre"]: [x["titulo"] for x in l["tarjetas"]] for l in c.get(f"/tableros/{tid}", headers=h).json()["listas"]}


def test_crear_y_ordenar(c, tablero):
    ana, t = tablero
    por_hacer, en_curso = t["listas"][0]["id"], t["listas"][1]["id"]
    ids = [c.post(f"/listas/{por_hacer}/tarjetas", headers=ana, json={"titulo": n}).json()["id"] for n in "ABC"]
    # Mover C al principio de la misma lista.
    c.post(f"/tarjetas/{ids[2]}/mover", headers=ana, json={"lista_id": por_hacer, "posicion": 0})
    assert titulos(c, ana, t["id"])["Por hacer"] == ["C", "A", "B"]
    # Mover A a "En curso" con posición fuera de rango -> queda al final (acotada).
    r = c.post(f"/tarjetas/{ids[0]}/mover", headers=ana, json={"lista_id": en_curso, "posicion": 99}).json()
    assert r["posicion"] == 0 and r["lista_id"] == en_curso
    vista = c.get(f"/tableros/{t['id']}", headers=ana).json()
    assert [x["posicion"] for x in vista["listas"][0]["tarjetas"]] == [0, 1]  # sin huecos
    # Reordenar listas: "Hecho" al principio.
    c.post(f"/listas/{t['listas'][2]['id']}/mover", headers=ana, json={"posicion": 0})
    assert list(titulos(c, ana, t["id"])) == ["Hecho", "Por hacer", "En curso"]
    act = c.get(f"/tableros/{t['id']}/actividad", headers=ana).json()
    assert any("movió «A»" in a for a in act)


def test_permisos_por_tablero(c, tablero):
    ana, t = tablero
    bob, bob_id = usuario(c, "bob@x.com")
    lista = t["listas"][0]["id"]
    # Bob no es miembro: el tablero "no existe" para él.
    assert c.get(f"/tableros/{t['id']}", headers=bob).status_code == 404
    assert c.post(f"/listas/{lista}/tarjetas", headers=bob, json={"titulo": "x"}).status_code == 404
    # Como lector: ve pero no edita, ni gestiona miembros.
    c.post(f"/tableros/{t['id']}/miembros", headers=ana, json={"email": "bob@x.com", "permiso": "lector"})
    assert c.get(f"/tableros/{t['id']}", headers=bob).status_code == 200
    assert c.post(f"/listas/{lista}/tarjetas", headers=bob, json={"titulo": "x"}).status_code == 403
    assert c.post(f"/tableros/{t['id']}/miembros", headers=bob,
                  json={"email": "ana@x.com", "permiso": "lector"}).status_code == 403
    # Ascendido a editor: ya puede crear, pero no borrar el tablero.
    c.post(f"/tableros/{t['id']}/miembros", headers=ana, json={"email": "bob@x.com", "permiso": "editor"})
    assert c.post(f"/listas/{lista}/tarjetas", headers=bob, json={"titulo": "x"}).status_code == 201
    assert c.delete(f"/tableros/{t['id']}", headers=bob).status_code == 403
    assert c.get("/tableros", headers=bob).json() == [{"id": t["id"], "nombre": "Lanzamiento", "permiso": "editor"}]
    assert c.delete(f"/tableros/{t['id']}", headers=ana).status_code == 204
    assert c.get("/tableros", headers=bob).json() == []


def test_no_mover_entre_tableros(c, tablero):
    ana, t = tablero
    otro = c.post("/tableros", headers=ana, json={"nombre": "Otro", "listas": ["X"]}).json()
    tid = c.post(f"/listas/{t['listas'][0]['id']}/tarjetas", headers=ana, json={"titulo": "A"}).json()["id"]
    r = c.post(f"/tarjetas/{tid}/mover", headers=ana, json={"lista_id": otro["listas"][0]["id"], "posicion": 0})
    assert r.status_code == 400


def test_asignacion_y_filtros(c, tablero):
    ana, t = tablero
    _, bob_id = usuario(c, "bob@x.com")
    lista = t["listas"][0]["id"]
    a = c.post(f"/listas/{lista}/tarjetas", headers=ana,
               json={"titulo": "A", "vence": "2026-05-01", "etiquetas": ["bug", "urgente"]}).json()["id"]
    c.post(f"/listas/{lista}/tarjetas", headers=ana, json={"titulo": "B", "vence": "2026-06-01", "etiquetas": ["doc"]})
    # Bob no es miembro: no se le puede asignar.
    assert c.post(f"/tarjetas/{a}/asignar", headers=ana, json={"usuario_id": bob_id}).status_code == 400
    c.post(f"/tableros/{t['id']}/miembros", headers=ana, json={"email": "bob@x.com", "permiso": "editor"})
    assert c.post(f"/tarjetas/{a}/asignar", headers=ana, json={"usuario_id": bob_id}).json()["asignado_id"] == bob_id
    base = f"/tableros/{t['id']}/buscar"
    assert [x["titulo"] for x in c.get(base, headers=ana, params={"etiqueta": "bug"}).json()] == ["A"]
    assert [x["titulo"] for x in c.get(base, headers=ana, params={"asignado_id": bob_id}).json()] == ["A"]
    assert [x["titulo"] for x in c.get(base, headers=ana, params={"vencidas": True}).json()] == ["A"]


def test_borrar_tarjeta_renumera(c, tablero):
    ana, t = tablero
    lista = t["listas"][0]["id"]
    ids = [c.post(f"/listas/{lista}/tarjetas", headers=ana, json={"titulo": n}).json()["id"] for n in "ABC"]
    assert c.delete(f"/tarjetas/{ids[0]}", headers=ana).status_code == 204
    vista = c.get(f"/tableros/{t['id']}", headers=ana).json()["listas"][0]["tarjetas"]
    assert [(x["titulo"], x["posicion"]) for x in vista] == [("B", 0), ("C", 1)]
