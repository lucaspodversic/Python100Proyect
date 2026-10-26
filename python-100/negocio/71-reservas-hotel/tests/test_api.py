"""Tests de la API HTTP: autenticación, roles, validaciones y reservas."""
from __future__ import annotations

from conftest import login


def test_salud(cliente):
    assert cliente.get("/salud").json() == {"estado": "ok"}


def test_registro_duplicado_y_login_invalido(cliente, registrar):
    registrar("bob@mail.com")
    r = cliente.post("/auth/registro", json={"email": "BOB@mail.com", "nombre": "B", "password": "secreta123"})
    assert r.status_code == 409  # el email se normaliza a minúsculas
    r = cliente.post("/auth/login", json={"email": "bob@mail.com", "password": "incorrecta"})
    assert r.status_code == 401


def test_password_corta_rechazada(cliente):
    r = cliente.post("/auth/registro", json={"email": "x@mail.com", "nombre": "X", "password": "corta"})
    assert r.status_code == 422


def test_solo_admin_crea_habitaciones(cliente, registrar):
    cab = registrar()
    r = cliente.post("/habitaciones", headers=cab,
                     json={"numero": "1", "tipo": "simple", "capacidad": 1, "precio_noche_centavos": 1})
    assert r.status_code == 403
    assert cliente.post("/habitaciones", json={}).status_code in (401, 422)


def test_numero_habitacion_unico(cliente, admin, habitacion):
    r = cliente.post("/habitaciones", headers=admin,
                     json={"numero": "101", "tipo": "doble", "capacidad": 2, "precio_noche_centavos": 1})
    assert r.status_code == 409


def test_reserva_y_total(cliente, registrar, habitacion):
    cab = registrar()
    r = cliente.post("/reservas", headers=cab, json={
        "habitacion_id": habitacion, "entrada": "2026-02-01", "salida": "2026-02-04", "huespedes": 2})
    assert r.status_code == 201, r.text
    assert r.json()["total_centavos"] == 3 * 50000


def test_solapamiento_rechazado_y_contiguo_permitido(cliente, registrar, habitacion):
    a, b = registrar("a@mail.com"), registrar("b@mail.com")
    base = {"habitacion_id": habitacion, "huespedes": 1}
    assert cliente.post("/reservas", headers=a, json={**base, "entrada": "2026-03-01", "salida": "2026-03-05"}).status_code == 201
    # Se solapa en las noches del 3 y 4.
    r = cliente.post("/reservas", headers=b, json={**base, "entrada": "2026-03-03", "salida": "2026-03-07"})
    assert r.status_code == 409
    # Contiguo: entra el día en que el otro sale -> permitido (intervalo semiabierto).
    r = cliente.post("/reservas", headers=b, json={**base, "entrada": "2026-03-05", "salida": "2026-03-07"})
    assert r.status_code == 201


def test_validaciones_de_reserva(cliente, registrar, habitacion):
    cab = registrar()
    base = {"habitacion_id": habitacion}
    # salida <= entrada -> 422 (validación Pydantic)
    assert cliente.post("/reservas", headers=cab, json={**base, "entrada": "2026-02-05", "salida": "2026-02-05", "huespedes": 1}).status_code == 422
    # pasado -> 400
    assert cliente.post("/reservas", headers=cab, json={**base, "entrada": "2026-01-01", "salida": "2026-01-03", "huespedes": 1}).status_code == 400
    # capacidad superada -> 400
    assert cliente.post("/reservas", headers=cab, json={**base, "entrada": "2026-02-01", "salida": "2026-02-03", "huespedes": 3}).status_code == 400
    # demasiadas noches -> 400
    assert cliente.post("/reservas", headers=cab, json={**base, "entrada": "2026-02-01", "salida": "2026-04-01", "huespedes": 1}).status_code == 400
    # habitación inexistente -> 404
    assert cliente.post("/reservas", headers=cab, json={"habitacion_id": 999, "entrada": "2026-02-01", "salida": "2026-02-03", "huespedes": 1}).status_code == 404


def test_disponibilidad_y_cancelacion(cliente, registrar, habitacion):
    cab = registrar()
    q = {"entrada": "2026-05-01", "salida": "2026-05-03", "huespedes": 2}
    assert len(cliente.get("/disponibilidad", params=q).json()) == 1
    rid = cliente.post("/reservas", headers=cab, json={"habitacion_id": habitacion, **q}).json()["id"]
    assert cliente.get("/disponibilidad", params=q).json() == []
    r = cliente.post(f"/reservas/{rid}/cancelar", headers=cab)
    assert r.status_code == 200 and r.json()["estado"] == "cancelada"
    # Cancelada -> la habitación vuelve a estar libre.
    assert len(cliente.get("/disponibilidad", params=q).json()) == 1
    assert cliente.post(f"/reservas/{rid}/cancelar", headers=cab).status_code == 409


def test_privacidad_entre_clientes(cliente, registrar, admin, habitacion):
    a, b = registrar("a@mail.com"), registrar("b@mail.com")
    rid = cliente.post("/reservas", headers=a, json={"habitacion_id": habitacion, "entrada": "2026-06-01",
                                                    "salida": "2026-06-02", "huespedes": 1}).json()["id"]
    assert cliente.get("/reservas", headers=b).json() == []
    assert cliente.post(f"/reservas/{rid}/cancelar", headers=b).status_code == 404
    assert len(cliente.get("/reservas", headers=admin).json()) == 1


def test_token_invalido(cliente):
    assert cliente.get("/reservas", headers={"Authorization": "Bearer nope"}).status_code == 401
