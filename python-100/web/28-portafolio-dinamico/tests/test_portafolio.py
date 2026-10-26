"""Tests del portafolio: público, API, contacto y panel admin."""
import re

import pytest
from werkzeug.security import generate_password_hash

from portafolio import crear_app, etiquetas_lista, slugificar


@pytest.fixture()
# El hash se genera en el test: la contraseña de prueba es "super-clave".
def app(tmp_path):
    return crear_app({"TESTING": True, "DATABASE": str(tmp_path / "p.db"), "SECRET_KEY": "t",
                      "ADMIN_USUARIO": "lucas", "ADMIN_HASH": generate_password_hash("super-clave")})


@pytest.fixture()
def c(app):
    return app.test_client()


# Extrae el token CSRF del HTML, como lo vería un navegador.
def tok(c, url="/admin/login"):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get(url).get_data(as_text=True)).group(1)


# Login como admin con las credenciales del fixture.
def entrar(c):
    c.post("/admin/login", data={"usuario": "lucas", "clave": "super-clave", "csrf_token": tok(c)})


# Alta de proyecto con datos por defecto; **kw permite pisar campos.
def crear(c, **kw):
    datos = {"titulo": "API de Tareas", "resumen": "CRUD con FastAPI", "etiquetas": "Python, FastAPI",
             "csrf_token": tok(c, "/admin"), **kw}
    return c.post("/admin/proyectos", data=datos)


# Slug sin acentos ni símbolos; etiquetas en minúscula, sin vacías ni repetidas.
def test_utilidades():
    assert slugificar("Mi Proyecto Ñandú!") == "mi-proyecto-nandu"
    assert etiquetas_lista("Python, flask ,python,, SQL") == ["python", "flask", "sql"]


# Sin sesión => 302 al login; clave mala => 401; clave buena => panel 200.
def test_admin_protegido_y_login(c):
    assert c.get("/admin").status_code == 302
    r = c.post("/admin/login", data={"usuario": "lucas", "clave": "mala", "csrf_token": tok(c)})
    assert r.status_code == 401
    entrar(c)
    assert c.get("/admin").status_code == 200


# Sin ADMIN_HASH ni siquiera una clave vacía permite entrar.
def test_panel_deshabilitado_sin_hash(tmp_path):
    c = crear_app({"DATABASE": str(tmp_path / "x.db"), "ADMIN_HASH": ""}).test_client()
    assert c.post("/admin/login", data={"usuario": "admin", "clave": "", "csrf_token": tok(c)}).status_code == 401


# Recorrido completo: alta, slug duplicado, orden, filtro, edición y borrado.
def test_crud_y_api(c):
    entrar(c)
    r = crear(c)
    assert r.headers["Location"].endswith("/proyecto/api-de-tareas")
    # El segundo es destacado, así que aparece primero en la API.
    crear(c, titulo="API de Tareas", destacado="on", etiquetas="go")  # slug duplicado -> -2
    api = c.get("/api/proyectos").get_json()
    assert [p["slug"] for p in api] == ["api-de-tareas-2", "api-de-tareas"]  # destacado primero
    assert [p["slug"] for p in c.get("/api/proyectos?etiqueta=fastapi").get_json()] == ["api-de-tareas"]
    # api[1] es el primer proyecto (el no destacado, slug "api-de-tareas").
    pid = api[1]["id"]
    c.post(f"/admin/proyectos/{pid}", data={"titulo": "Nuevo", "resumen": "r", "csrf_token": tok(c, "/admin")})
    assert "Nuevo" in c.get("/proyecto/api-de-tareas").get_data(as_text=True)
    # Tras borrar, el detalle por slug da 404.
    c.post(f"/admin/proyectos/{pid}/borrar", data={"csrf_token": tok(c, "/admin")})
    assert c.get("/proyecto/api-de-tareas").status_code == 404


# URL con esquema javascript: y título vacío => 400.
def test_validaciones_admin(c):
    entrar(c)
    assert crear(c, url_repo="javascript:alert(1)").status_code == 400
    assert crear(c, titulo="").status_code == 400


# "#fastapi" aparece porque la plantilla muestra las etiquetas con "#".
def test_filtro_html(c):
    entrar(c)
    crear(c)
    html = c.get("/?etiqueta=python").get_data(as_text=True)
    assert "API de Tareas" in html and "#fastapi" in html


# Tres envíos: email inválido (400), bot con honeypot (se descarta en
# silencio) y uno válido. En el panel solo debe aparecer el válido.
def test_contacto_valido_honeypot_y_csrf(c, app):
    t = tok(c, "/contacto")
    assert c.post("/contacto", data={"nombre": "Ana", "email": "mal", "texto": "hola hola hola", "csrf_token": t}).status_code == 400
    c.post("/contacto", data={"nombre": "Bot", "email": "b@b.com", "texto": "spam spam spam", "sitio_web": "x", "csrf_token": t})
    c.post("/contacto", data={"nombre": "Ana", "email": "ana@ej.com", "texto": "Me interesa tu trabajo", "csrf_token": t})
    assert c.post("/contacto", data={"nombre": "x"}).status_code == 400  # sin CSRF
    entrar(c)
    html = c.get("/admin").get_data(as_text=True)
    assert "Me interesa tu trabajo" in html and "spam" not in html
