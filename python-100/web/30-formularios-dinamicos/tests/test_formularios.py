"""Tests del esquema, validación y API de formularios."""
import csv
import io

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from formularios.app import crear_app
from formularios.esquema import Campo, validar_respuesta

# Un formulario que usa todos los tipos. El título tiene HTML a propósito,
# para comprobar que se escapa.
DEF = {
    "titulo": "Encuesta <b>café</b>",
    "campos": [
        {"nombre": "nombre", "etiqueta": "Tu nombre", "tipo": "texto", "requerido": True, "largo_max": 20},
        {"nombre": "email", "etiqueta": "Email", "tipo": "email"},
        {"nombre": "edad", "etiqueta": "Edad", "tipo": "numero", "minimo": 18, "maximo": 99},
        {"nombre": "favorito", "etiqueta": "Favorito", "tipo": "seleccion", "opciones": ["espresso", "latte"], "requerido": True},
        {"nombre": "extras", "etiqueta": "Extras", "tipo": "casillas", "opciones": ["azúcar", "leche", "canela"]},
        {"nombre": "visita", "etiqueta": "Última visita", "tipo": "fecha"},
    ],
}


@pytest.fixture()
# Crea el formulario y devuelve cliente, slug y header del dueño.
def ctx():
    c = TestClient(crear_app())
    f = c.post("/api/formularios", json=DEF).json()
    return c, f["slug"], {"X-Token-Dueno": f["token_dueno"]}


# Selección con 1 opción, nombre con mayúsculas/espacios y mín > máx.
def test_definiciones_invalidas():
    with pytest.raises(ValidationError):
        Campo(nombre="x", etiqueta="X", tipo="seleccion", opciones=["solo una"])
    with pytest.raises(ValidationError):
        Campo(nombre="Mal Nombre", etiqueta="X", tipo="texto")
    with pytest.raises(ValidationError):
        Campo(nombre="n", etiqueta="N", tipo="numero", minimo=5, maximo=1)


def test_validacion_por_tipo():
    campos = [Campo(**c) for c in DEF["campos"]]
    # Respuesta válida: espacios recortados, "30" texto => 30 entero, casillas
    # sin duplicados y ordenadas. Email/opcionales omitidos no dan error.
    limpio, err = validar_respuesta(campos, {"nombre": " Ana ", "edad": "30", "favorito": "latte",
                                              "extras": ["canela", "azúcar", "canela"], "visita": "2026-10-01"})
    assert err == {} and limpio["nombre"] == "Ana" and limpio["edad"] == 30
    assert limpio["extras"] == ["azúcar", "canela"]  # sin duplicados, en el orden de las opciones
    # Un error por campo: 30 > largo_max 20, email sin @, 10 < mínimo 18,
    # "mate" no es opción, "oro" tampoco, "ayer" no es fecha ISO.
    _, err = validar_respuesta(campos, {"nombre": "x" * 30, "email": "no", "edad": 10, "favorito": "mate",
                                        "extras": ["oro"], "visita": "ayer"})
    assert set(err) == {"nombre", "email", "edad", "favorito", "extras", "visita"}
    # Vacío: solo se quejan los dos requeridos (nombre y favorito).
    _, err = validar_respuesta(campos, {})
    assert err == {"nombre": "Campo obligatorio", "favorito": "Campo obligatorio"}


def test_nombres_duplicados_api():
    c = TestClient(crear_app())
    # El mismo campo dos veces => nombres duplicados => 422.
    d = {"titulo": "x", "campos": [{"nombre": "a", "etiqueta": "A", "tipo": "texto"}] * 2}
    assert c.post("/api/formularios", json=d).status_code == 422


def test_responder_json_y_resumen(ctx):
    c, slug, dueno = ctx
    url = f"/api/formularios/{slug}/responder"
    assert c.post(url, json={"nombre": "Ana", "favorito": "latte", "edad": 30, "extras": ["leche"]}).status_code == 201
    assert c.post(url, json={"nombre": "Beto", "favorito": "espresso", "edad": 40, "extras": ["leche", "canela"]}).status_code == 201
    r = c.post(url, json={"favorito": "nada"})
    assert r.status_code == 422 and "nombre" in r.json()["detail"]["errores"]
    # La respuesta inválida no cuenta: total 2. Extras: leche en ambas (2),
    # canela en una (1), azúcar en ninguna (0). Edad: (30 + 40) / 2 = 35.
    res = c.get(f"/api/formularios/{slug}/resumen", headers=dueno).json()
    assert res["total"] == 2
    assert res["campos"]["favorito"] == {"espresso": 1, "latte": 1}
    assert res["campos"]["extras"] == {"azúcar": 0, "leche": 2, "canela": 1}
    assert res["campos"]["edad"] == {"promedio": 35, "minimo": 30, "maximo": 40}


# Sin header o con token incorrecto => 403.
def test_solo_el_dueno_ve_respuestas(ctx):
    c, slug, _ = ctx
    assert c.get(f"/api/formularios/{slug}/respuestas").status_code == 403
    assert c.get(f"/api/formularios/{slug}/respuestas", headers={"X-Token-Dueno": "x"}).status_code == 403


def test_html_escapado_y_envio_form(ctx):
    c, slug, dueno = ctx
    html = c.get(f"/f/{slug}").text
    # El <b> del título aparece escapado (&lt;b&gt;), no como etiqueta real.
    assert "<b>café</b>" not in html and "&lt;b&gt;" in html and "type='checkbox'" in html
    r = c.post(f"/f/{slug}", data={"nombre": "Caro", "favorito": "latte", "extras": ["azúcar", "canela"]})
    assert r.status_code == 200 and "Gracias" in r.text
    # Envío HTML inválido => 422 con el formulario y el mensaje de error.
    r = c.post(f"/f/{slug}", data={"nombre": ""})
    assert r.status_code == 422 and "Campo obligatorio" in r.text
    assert c.get(f"/api/formularios/{slug}/respuestas", headers=dueno).json()[0]["extras"] == ["azúcar", "canela"]


# Un nombre que es una fórmula de Excel debe salir con apóstrofo delante, y
# las casillas unidas con "; ".
def test_export_csv_seguro(ctx):
    c, slug, dueno = ctx
    c.post(f"/api/formularios/{slug}/responder", json={"nombre": "=HYPERLINK(1)", "favorito": "latte", "extras": ["leche", "canela"]})
    texto = c.get(f"/api/formularios/{slug}/export.csv", headers=dueno).text
    filas = list(csv.DictReader(io.StringIO(texto)))
    assert filas[0]["nombre"] == "'=HYPERLINK(1)" and filas[0]["extras"] == "leche; canela"


# Cerrado => la definición dice abierto False y responder da 409.
# Un slug inexistente => 404.
def test_cerrar(ctx):
    c, slug, dueno = ctx
    c.post(f"/api/formularios/{slug}/cerrar", headers=dueno)
    assert c.get(f"/api/formularios/{slug}").json()["abierto"] is False
    assert c.post(f"/api/formularios/{slug}/responder", json={"nombre": "x", "favorito": "latte"}).status_code == 409
    assert c.get("/api/formularios/nada").status_code == 404
