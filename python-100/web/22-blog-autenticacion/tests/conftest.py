"""Fixtures compartidas: app con base temporal y helpers de CSRF/login."""
import re

import pytest

from blog import crear_app


# tmp_path es un directorio temporal distinto por test: bases aisladas.
@pytest.fixture()
def app(tmp_path):
    """App Flask con una base SQLite en un archivo temporal."""
    # SECRET_KEY fija para que las cookies firmadas sean reproducibles en tests.
    return crear_app({"TESTING": True, "DATABASE": str(tmp_path / "t.db"), "SECRET_KEY": "test"})


@pytest.fixture()
# test_client mantiene cookies entre pedidos, como un navegador.
def cliente(app):
    return app.test_client()


def csrf(cliente, url: str = "/login") -> str:
    """Hace GET a una página con formulario y extrae el token CSRF."""
    # El GET crea la sesión con el token; luego se lo extrae del input oculto,
    # igual que haría el navegador al renderizar el formulario.
    html = cliente.get(url).get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def registrar_y_entrar(cliente, nombre: str = "lucas", clave: str = "clave-segura") -> None:
    """Helper: crea la cuenta e inicia sesión."""
    cliente.post("/registro", data={"nombre": nombre, "clave": clave, "csrf_token": csrf(cliente, "/registro")})
    cliente.post("/login", data={"nombre": nombre, "clave": clave, "csrf_token": csrf(cliente)})
