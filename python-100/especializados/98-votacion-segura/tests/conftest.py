"""Fixtures compartidas.

La clave RSA es lo más caro de crear, así que generamos UNA de 1024 bits por
sesión de tests (en producción se usan ≥ 2048). La elección y la app sí son
nuevas en cada test, con SQLite en memoria (no quedan archivos .db).
"""
import pytest
from fastapi.testclient import TestClient

from votacion.api import create_app
from votacion.cripto import Autoridad
from votacion.servicio import Eleccion

ADMIN = "admin-secreto-de-prueba-123"
H_ADMIN = {"x-admin-token": ADMIN}


@pytest.fixture(scope="session")
def autoridad():
    return Autoridad(bits=1024)


@pytest.fixture()
def eleccion(autoridad):
    return Eleccion("test-2026", ["Ana", "Beto", "En blanco"], autoridad=autoridad)


@pytest.fixture()
def cliente(eleccion):
    return TestClient(create_app(ADMIN, eleccion=eleccion))
