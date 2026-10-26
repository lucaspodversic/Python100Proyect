"""Fixtures compartidas: app aislada con BD temporal y reloj fijo."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.main import crear_app

# "Hoy" fijo para que los tests no dependan de la fecha real.
HOY = date(2026, 1, 10)
ADMIN = ("admin@hotel.local", "clave-admin-123")


@pytest.fixture()
def app(tmp_path):
    """App con su propia base SQLite en un directorio temporal."""
    return crear_app(f"sqlite:///{tmp_path / 'hotel.db'}", ADMIN[0], ADMIN[1], reloj=lambda: HOY)


@pytest.fixture()
def cliente(app):
    """Cliente HTTP de pruebas (no abre puertos reales)."""
    return TestClient(app)


def login(cliente: TestClient, email: str, password: str) -> dict[str, str]:
    """Inicia sesión y devuelve la cabecera Authorization lista para usar."""
    r = cliente.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture()
def admin(cliente):
    """Cabeceras del administrador."""
    return login(cliente, *ADMIN)


@pytest.fixture()
def registrar(cliente):
    """Fábrica: registra un cliente y devuelve sus cabeceras."""
    def _registrar(email: str = "ana@mail.com") -> dict[str, str]:
        r = cliente.post("/auth/registro", json={"email": email, "nombre": "Ana", "password": "secreta123"})
        assert r.status_code == 201, r.text
        return login(cliente, email, "secreta123")
    return _registrar


@pytest.fixture()
def habitacion(cliente, admin):
    """Crea una habitación doble y devuelve su id."""
    r = cliente.post("/habitaciones", headers=admin,
                     json={"numero": "101", "tipo": "doble", "capacidad": 2, "precio_noche_centavos": 50000})
    assert r.status_code == 201, r.text
    return r.json()["id"]
