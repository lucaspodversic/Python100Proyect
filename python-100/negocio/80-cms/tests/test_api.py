"""Tests de la API del CMS."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import crear_app

ADMIN = ("admin@cms.local", "clave-admin-123")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class Reloj:
    """Reloj controlable que empieza el 1/8/2026 a las 10:00."""
    def __init__(self):
        """Hora inicial fija."""
        self.t = datetime(2026, 8, 1, 10)

    def __call__(self):
        """Devuelve la hora simulada."""
        return self.t


@pytest.fixture()
def reloj():
    """Un reloj nuevo por test."""
    return Reloj()


@pytest.fixture()
def c(tmp_path, reloj):
    """Cliente con base y carpeta de medios nuevas en tmp_path."""
    return TestClient(crear_app(f"sqlite:///{tmp_path / 'c.db'}", tmp_path / "medios", *ADMIN, reloj=reloj))


def login(c, email, pw="secreta123"):
    """Cabecera Authorization para el usuario."""
    return {"Authorization": "Bearer " + c.post("/auth/login", json={"email": email, "password": pw}).json()["token"]}


@pytest.fixture()
def gente(c):
    """Dos autores (autor, otro) y un editor; devuelve sus cabeceras."""
    out = {}
    for email, rol in (("autor@x.com", None), ("otro@x.com", None), ("editor@x.com", "editor")):
        uid = c.post("/auth/registro", json={"email": email, "nombre": "x", "password": "secreta123"}).json()["id"]
        if rol:
            c.patch(f"/usuarios/{uid}/rol", headers=login(c, *ADMIN), json={"rol": rol})
        out[email.split("@")[0]] = login(c, email)
    return out


def nuevo(c, h, titulo="Hola Mundo", etiquetas=("python",)):
    """Crea un artículo con cuerpo Markdown fijo y devuelve el JSON."""
    return c.post("/articulos", headers=h, json={"titulo": titulo, "cuerpo": "Texto **inicial**",
                                                 "etiquetas": list(etiquetas)}).json()


def test_slugs_unicos(c, gente):
    """'¡Hola, mundo!' se normaliza al mismo slug que 'Hola Mundo', así que recibe el sufijo
    -2.
    """
    assert nuevo(c, gente["autor"])["slug"] == "hola-mundo"
    assert nuevo(c, gente["autor"], "¡Hola, mundo!")["slug"] == "hola-mundo-2"


def test_flujo_editorial(c, gente):
    """Un borrador no se publica directo (409); el autor envía pero no publica (403); un
    artículo ajeno es invisible (404). Hasta publicar no hay página pública; después el
    Markdown se ve como HTML. Lo publicado ya no lo edita el autor, y al archivarlo
    desaparece del listado público.
    """
    a = nuevo(c, gente["autor"])
    flujo = lambda h, acc, **kw: c.post(f"/articulos/{a['id']}/flujo", headers=gente[h], json={"accion": acc, **kw})  # noqa: E731
    assert flujo("autor", "publicar").status_code == 409            # borrador no se publica directo
    assert flujo("autor", "enviar").json()["estado"] == "en_revision"
    assert flujo("autor", "publicar").status_code == 403            # autor no publica
    assert flujo("otro", "rechazar").status_code == 404             # ajeno: invisible
    assert c.get("/publico/articulos/hola-mundo").status_code == 404
    assert flujo("editor", "publicar").json()["estado"] == "publicado"
    pub = c.get("/publico/articulos/hola-mundo").json()
    assert pub["html"] == "<p>Texto <strong>inicial</strong></p>"
    # El autor ya no puede editar lo publicado.
    assert c.put(f"/articulos/{a['id']}", headers=gente["autor"],
                 json={"version": 1, "titulo": "Nuevo", "cuerpo": "x"}).status_code == 403
    assert flujo("editor", "archivar").status_code == 200
    assert c.get("/publico/articulos").json() == []


def test_publicacion_programada(c, gente, reloj):
    """Publicado para mañana: hoy no aparece; dos días después sí, y el filtro por etiqueta no
    distingue mayúsculas ('Noticias' se guardó como 'noticias').
    """
    a = nuevo(c, gente["autor"], etiquetas=["Noticias"])
    c.post(f"/articulos/{a['id']}/flujo", headers=gente["autor"], json={"accion": "enviar"})
    manana = (reloj.t + timedelta(days=1)).isoformat()
    c.post(f"/articulos/{a['id']}/flujo", headers=gente["editor"], json={"accion": "publicar", "publicar_en": manana})
    assert c.get("/publico/articulos").json() == []
    reloj.t += timedelta(days=2)
    assert c.get("/publico/articulos", params={"etiqueta": "noticias"}).json() == [{"slug": "hola-mundo", "titulo": "Hola Mundo"}]


def test_bloqueo_optimista_y_revisiones(c, gente):
    """La edición con versión 1 pasa a 2; otra edición con la versión 1 vieja es un conflicto
    (409) y no pisa nada. Restaurar la revisión 1 crea la versión 3 con el título
    original. Cada autor lista solo lo suyo.
    """
    a = nuevo(c, gente["autor"])
    url = f"/articulos/{a['id']}"
    r1 = c.put(url, headers=gente["autor"], json={"version": 1, "titulo": "Versión dos", "cuerpo": "B"})
    assert r1.json()["version"] == 2
    # Otra pestaña con la versión vieja: conflicto, no pisa.
    r2 = c.put(url, headers=gente["editor"], json={"version": 1, "titulo": "Pisada", "cuerpo": "C"})
    assert r2.status_code == 409
    assert [r["numero"] for r in c.get(f"{url}/revisiones", headers=gente["autor"]).json()] == [1, 2]
    r = c.post(f"{url}/revisiones/1/restaurar", headers=gente["autor"]).json()
    assert r["titulo"] == "Hola Mundo" and r["version"] == 3
    assert len(c.get("/articulos", headers=gente["autor"]).json()) == 1
    assert len(c.get("/articulos", headers=gente["otro"]).json()) == 0


def test_subida_de_medios(c, gente):
    """El nombre con '../..' se ignora: se guarda con un nombre aleatorio. La descarga es
    idéntica y con nosniff. Un PHP con extensión .png se rechaza por contenido (415) y
    un archivo de más de 2 MiB da 413. Pedir rutas con '..' da 404.
    """
    h = gente["autor"]
    r = c.post("/medios", headers=h, files={"archivo": ("../../etc/foto.png", PNG, "image/png")})
    assert r.status_code == 201 and r.json()["url"].endswith(".png") and ".." not in r.json()["url"]
    descarga = c.get(r.json()["url"])
    assert descarga.content == PNG and descarga.headers["x-content-type-options"] == "nosniff"
    # Un PHP disfrazado de imagen se rechaza por contenido.
    assert c.post("/medios", headers=h, files={"archivo": ("x.png", b"<?php system($_GET[1]);", "image/png")}).status_code == 415
    grande = PNG + b"\x00" * (2 * 1024 * 1024)
    assert c.post("/medios", headers=h, files={"archivo": ("g.png", grande, "image/png")}).status_code == 413
    assert c.get("/medios/..%2F..%2Fsecreto").status_code == 404
