"""Fixtures: app aislada, admin, empleado y lector."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import crear_app

ADMIN = ("admin@tienda.local", "clave-admin-123")


def login(c: TestClient, email: str, password: str) -> dict[str, str]:
    r = c.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture()
def app(tmp_path):
    return crear_app(f"sqlite:///{tmp_path / 'inv.db'}", ADMIN[0], ADMIN[1])


@pytest.fixture()
def c(app):
    return TestClient(app)


@pytest.fixture()
def admin(c):
    return login(c, *ADMIN)


@pytest.fixture()
def lector(c):
    r = c.post("/auth/registro", json={"email": "lector@t.com", "nombre": "L", "password": "secreta123"})
    assert r.status_code == 201
    cab = login(c, "lector@t.com", "secreta123")
    cab["_id"] = str(r.json()["id"])  # guardamos el id para promoverlo
    return cab


@pytest.fixture()
def empleado(c, admin):
    r = c.post("/auth/registro", json={"email": "emp@t.com", "nombre": "E", "password": "secreta123"})
    c.patch(f"/usuarios/{r.json()['id']}/rol", headers=admin, json={"rol": "empleado"})
    return login(c, "emp@t.com", "secreta123")


@pytest.fixture()
def producto(c, admin):
    prov = c.post("/proveedores", headers=admin, json={"nombre": "ACME", "email": "ventas@acme.com"}).json()
    r = c.post("/productos", headers=admin, json={"sku": "CAF-001", "nombre": "Café 500g",
                                                  "precio_centavos": 450000, "stock_minimo": 5,
                                                  "proveedor_id": prov["id"]})
    assert r.status_code == 201, r.text
    return {**r.json(), "proveedor_id": prov["id"]}
