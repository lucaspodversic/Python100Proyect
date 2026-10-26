"""Tests de la API de RRHH (TestClient + SQLite temporal)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import crear_app

ADMIN = ("admin@rrhh.local", "clave-admin-123")


def login(c, email, pw="secreta123"):
    r = c.post("/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture()
def c(tmp_path):
    return TestClient(crear_app(f"sqlite:///{tmp_path / 'rrhh.db'}", *ADMIN))


@pytest.fixture()
def admin(c):
    return login(c, *ADMIN)


@pytest.fixture()
def ana(c, admin):
    """Empleada con usuario vinculado; devuelve (cabeceras, id_empleado)."""
    uid = c.post("/auth/registro", json={"email": "ana@x.com", "nombre": "Ana", "password": "secreta123"}).json()["id"]
    emp = c.post("/empleados", headers=admin, json={
        "legajo": "A-001", "nombre": "Ana", "departamento": "IT", "puesto": "Dev",
        "fecha_ingreso": "2024-03-01", "salario_bruto_centavos": 90_000_00, "usuario_id": uid})
    assert emp.status_code == 201, emp.text
    return login(c, "ana@x.com"), emp.json()["id"]


def test_empleado_no_gestiona(c, ana):
    cab, _ = ana
    assert c.get("/empleados", headers=cab).status_code == 403
    assert c.post("/nominas/2026-01", headers=cab).status_code == 403
    assert c.get("/yo", headers=cab).json()["legajo"] == "A-001"


def test_legajo_unico(c, admin, ana):
    r = c.post("/empleados", headers=admin, json={
        "legajo": "A-001", "nombre": "X", "departamento": "IT", "puesto": "X",
        "fecha_ingreso": "2024-01-01", "salario_bruto_centavos": 1})
    assert r.status_code == 409


def test_ausencias_solapamiento_y_saldo(c, ana):
    cab, _ = ana
    r = c.post("/yo/ausencias", headers=cab, json={"tipo": "vacaciones", "desde": "2026-01-05", "hasta": "2026-01-14"})
    assert r.status_code == 201 and r.json()["dias"] == 10
    # Se solapa el 14.
    assert c.post("/yo/ausencias", headers=cab, json={"tipo": "enfermedad", "desde": "2026-01-14", "hasta": "2026-01-15"}).status_code == 409
    # Saldo: quedan 4 de 14, pedir 5 falla.
    r = c.post("/yo/ausencias", headers=cab, json={"tipo": "vacaciones", "desde": "2026-03-01", "hasta": "2026-03-05"})
    assert r.status_code == 409 and "quedan 4" in r.json()["detail"]
    assert c.get("/yo/vacaciones", params={"anio": 2026}, headers=cab).json()["disponibles"] == 4
    assert c.post("/yo/ausencias", headers=cab, json={"tipo": "sin_goce", "desde": "2026-02-02", "hasta": "2026-02-01"}).status_code == 400


def test_aprobacion_y_no_autoaprobacion(c, admin, ana):
    cab, _ = ana
    aid = c.post("/yo/ausencias", headers=cab, json={"tipo": "sin_goce", "desde": "2026-02-02", "hasta": "2026-02-04"}).json()["id"]
    assert c.post(f"/ausencias/{aid}/aprobar", headers=cab).status_code == 403
    assert len(c.get("/ausencias", headers=admin).json()) == 1
    r = c.post(f"/ausencias/{aid}/aprobar", headers=admin)
    assert r.json()["estado"] == "aprobada"
    assert c.post(f"/ausencias/{aid}/rechazar", headers=admin).status_code == 409


def test_liquidacion_con_descuento_e_idempotencia(c, admin, ana):
    cab, _ = ana
    aid = c.post("/yo/ausencias", headers=cab, json={"tipo": "sin_goce", "desde": "2026-02-02", "hasta": "2026-02-04"}).json()["id"]
    c.post(f"/ausencias/{aid}/aprobar", headers=admin)
    r = c.post("/nominas/2026-02", headers=admin)
    assert r.status_code == 201
    n = r.json()[0]
    assert n["descuento_ausencias_centavos"] == 9_000_00
    assert n["neto_centavos"] == 81_000_00 - 13_770_00
    assert c.post("/nominas/2026-02", headers=admin).status_code == 409   # no se liquida dos veces
    assert c.post("/nominas/2026-99", headers=admin).status_code == 400
    assert len(c.get("/yo/nominas", headers=cab).json()) == 1


def test_baja_excluye_de_nomina_y_reporte(c, admin, ana):
    _, eid = ana
    c.post("/empleados", headers=admin, json={"legajo": "B-1", "nombre": "Beto", "departamento": "Ventas",
                                              "puesto": "Vendedor", "fecha_ingreso": "2025-01-01",
                                              "salario_bruto_centavos": 50_000_00})
    assert c.get("/reportes/masa-salarial", headers=admin).json() == {"IT": 90_000_00, "Ventas": 50_000_00}
    c.post(f"/empleados/{eid}/baja", headers=admin)
    assert len(c.post("/nominas/2026-03", headers=admin).json()) == 1


def test_promocion_a_rrhh(c, admin, ana):
    c.post("/auth/registro", json={"email": "rh@x.com", "nombre": "RH", "password": "secreta123"})
    rh = login(c, "rh@x.com")
    assert c.get("/empleados", headers=rh).status_code == 403
    c.patch("/usuarios/3/rol", headers=admin, json={"rol": "rrhh"})
    assert c.get("/empleados", headers=rh).status_code == 200
