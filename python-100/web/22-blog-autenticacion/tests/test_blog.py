"""Tests funcionales del blog: auth, CSRF, permisos y XSS."""
import sqlite3

from tests.conftest import csrf, registrar_y_entrar


# Se mira la base directamente: la clave no debe aparecer y el hash debe
# llevar el prefijo del algoritmo (scrypt en Werkzeug 3; pbkdf2 en versiones viejas).
def test_registro_guarda_hash_no_texto_plano(cliente, app):
    registrar_y_entrar(cliente)
    con = sqlite3.connect(app.config["DATABASE"])
    hash_guardado = con.execute("SELECT hash_clave FROM usuarios").fetchone()[0]
    assert "clave-segura" not in hash_guardado and hash_guardado.startswith(("scrypt:", "pbkdf2:"))


# "ab" (<3 caracteres) y "corta" (<8) dan 400; el primer "pepe" válido
# redirige (302) al login; el segundo choca con UNIQUE.
def test_registro_valida_datos_y_duplicados(cliente):
    t = csrf(cliente, "/registro")
    assert cliente.post("/registro", data={"nombre": "ab", "clave": "12345678", "csrf_token": t}).status_code == 400
    assert cliente.post("/registro", data={"nombre": "pepe", "clave": "corta", "csrf_token": t}).status_code == 400
    assert cliente.post("/registro", data={"nombre": "pepe", "clave": "12345678", "csrf_token": t}).status_code == 302
    r = cliente.post("/registro", data={"nombre": "pepe", "clave": "12345678", "csrf_token": t})
    assert "ya existe" in r.get_data(as_text=True)


# Sin token y con token inventado: ambos 400 antes de llegar a la vista.
def test_post_sin_csrf_es_rechazado(cliente):
    cliente.get("/login")
    assert cliente.post("/login", data={"nombre": "x", "clave": "y"}).status_code == 400
    assert cliente.post("/login", data={"nombre": "x", "clave": "y", "csrf_token": "falso"}).status_code == 400


# El mensaje no dice si falló el usuario o la clave (evita enumerar usuarios).
def test_login_incorrecto_mensaje_generico(cliente):
    registrar_y_entrar(cliente)
    cliente.post("/logout", data={"csrf_token": csrf(cliente, "/")})
    r = cliente.post("/login", data={"nombre": "lucas", "clave": "mal", "csrf_token": csrf(cliente)})
    assert r.status_code == 401 and "incorrectos" in r.get_data(as_text=True)


# Sin sesión: 302 a /login?siguiente=/nuevo.
def test_nuevo_requiere_login(cliente):
    r = cliente.get("/nuevo")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


# Ciclo de vida completo; la URL del artículo sale del Location del redirect.
def test_publicar_editar_y_borrar(cliente):
    registrar_y_entrar(cliente)
    r = cliente.post("/nuevo", data={"titulo": "Hola", "cuerpo": "Mundo", "csrf_token": csrf(cliente, "/nuevo")})
    url = r.headers["Location"]
    assert "Hola" in cliente.get(url).get_data(as_text=True)
    cliente.post(url + "/editar", data={"titulo": "Chau", "cuerpo": "Mundo", "csrf_token": csrf(cliente, url + "/editar")})
    assert "Chau" in cliente.get("/").get_data(as_text=True)
    cliente.post(url + "/borrar", data={"csrf_token": csrf(cliente, url)})
    assert cliente.get(url).status_code == 404


# Dos clientes = dos navegadores con sesiones distintas.
def test_solo_el_autor_puede_editar(app):
    a, b = app.test_client(), app.test_client()
    registrar_y_entrar(a, "autor")
    url = a.post("/nuevo", data={"titulo": "Mío", "cuerpo": "x", "csrf_token": csrf(a, "/nuevo")}).headers["Location"]
    registrar_y_entrar(b, "intruso")
    assert b.get(url + "/editar").status_code == 403
    assert b.post(url + "/borrar", data={"csrf_token": csrf(b, "/")}).status_code == 403


# Jinja2 convierte < en &lt;: el script se muestra como texto, no se ejecuta.
def test_xss_escapado(cliente):
    registrar_y_entrar(cliente)
    url = cliente.post("/nuevo", data={"titulo": "<script>alert(1)</script>", "cuerpo": "x",
                                      "csrf_token": csrf(cliente, "/nuevo")}).headers["Location"]
    html = cliente.get(url).get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html


# "//malicioso.example" se descarta y se redirige al inicio ("/").
def test_no_hay_open_redirect(cliente):
    registrar_y_entrar(cliente)
    cliente.post("/logout", data={"csrf_token": csrf(cliente, "/")})
    r = cliente.post("/login?siguiente=//malicioso.example", data={"nombre": "lucas", "clave": "clave-segura",
                                                                   "csrf_token": csrf(cliente)})
    assert r.headers["Location"] == "/"
