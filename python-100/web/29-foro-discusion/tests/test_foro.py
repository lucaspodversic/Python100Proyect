"""Tests del foro: seguridad, hilos, árbol de respuestas, votos y ranking."""
import pytest
from fastapi.testclient import TestClient

from foro.app import crear_app
from foro.ranking import puntaje_hot
from foro.seguridad import hashear_clave, huella_token, verificar_clave


# 1.800.000.000 ≈ enero 2027: posterior a EPOCA, como en la vida real.
class Reloj:
    def __init__(self):
        self.t = 1_800_000_000.0

    def __call__(self):
        return self.t


@pytest.fixture()
def ctx():
    reloj = Reloj()
    c = TestClient(crear_app(":memory:", reloj))

    # Helper: registra, loguea y devuelve el header Authorization listo.
    def usuario(nombre):
        c.post("/registro", json={"nombre": nombre, "clave": "clave-larga-1"})
        t = c.post("/login", json={"nombre": nombre, "clave": "clave-larga-1"}).json()["token"]
        return {"Authorization": f"Bearer {t}"}
    return c, reloj, usuario


# Formato "scrypt$...", verificación correcta/incorrecta, sal distinta en
# cada hash y huella SHA-256 de 64 caracteres hex.
def test_hash_y_tokens():
    h = hashear_clave("secreta123")
    assert h.startswith("scrypt$") and verificar_clave("secreta123", h) and not verificar_clave("otra", h)
    assert hashear_clave("secreta123") != h  # sal distinta cada vez
    assert len(huella_token("abc")) == 64


def test_ranking_hot():
    # Un hilo con 10 votos hoy le gana a uno con 100 votos de hace 2 días
    # Cuentas: hoy => log10(10) = 1. Hace 2 días => log10(100) = 2, pero pierde
    # 172800 / 45000 = 3,84 por antigüedad => 2 - 3,84 = -1,84 < 1.
    assert puntaje_hot(10, 1_800_000_000) > puntaje_hot(100, 1_800_000_000 - 2 * 86400)


# Nombre repetido 409, con espacios 422, clave mala 401, sin token o con
# token falso 401.
def test_registro_login_y_errores(ctx):
    c, _, usuario = ctx
    usuario("ana")
    assert c.post("/registro", json={"nombre": "ana", "clave": "otra-clave-1"}).status_code == 409
    assert c.post("/registro", json={"nombre": "a b c", "clave": "otra-clave-1"}).status_code == 422
    assert c.post("/login", json={"nombre": "ana", "clave": "incorrecta"}).status_code == 401
    assert c.post("/hilos", json={"titulo": "abc", "texto": "x"}).status_code == 401
    assert c.post("/hilos", json={"titulo": "abc", "texto": "x"},
                  headers={"Authorization": "Bearer falso"}).status_code == 401


# Tras el logout el token deja de servir. Un token nuevo vence a los 7
# días: se adelanta el reloj 8 días y da 401.
def test_token_vence_y_logout(ctx):
    c, reloj, usuario = ctx
    h = usuario("ana")
    assert c.post("/hilos", json={"titulo": "Hola", "texto": "x"}, headers=h).status_code == 201
    c.post("/logout", headers=h)
    assert c.post("/hilos", json={"titulo": "Hola", "texto": "x"}, headers=h).status_code == 401
    h2 = usuario("ana")
    reloj.t += 8 * 86400
    assert c.post("/hilos", json={"titulo": "Hola", "texto": "x"}, headers=h2).status_code == 401


# ana vota +1 dos veces => sigue en 1 (un voto por usuario). beto vota -1
# => 0. beto quita su voto (0) => vuelve a 1. Objeto inexistente => 404.
def test_votos_unicos_y_cambiables(ctx):
    c, _, usuario = ctx
    a, b = usuario("ana"), usuario("beto")
    hid = c.post("/hilos", json={"titulo": "Python vs Go", "texto": "?"}, headers=a).json()["id"]
    assert c.post("/votos", json={"tipo": "hilo", "id": hid, "valor": 1}, headers=a).json() == {"puntaje": 1}
    assert c.post("/votos", json={"tipo": "hilo", "id": hid, "valor": 1}, headers=a).json() == {"puntaje": 1}
    assert c.post("/votos", json={"tipo": "hilo", "id": hid, "valor": -1}, headers=b).json() == {"puntaje": 0}
    assert c.post("/votos", json={"tipo": "hilo", "id": hid, "valor": 0}, headers=b).json() == {"puntaje": 1}
    assert c.post("/votos", json={"tipo": "hilo", "id": 999, "valor": 1}, headers=a).status_code == 404


# r1 "primera" (beto) tiene una hija; r2 "segunda" recibe +1 y pasa
# adelante. Solo beto puede borrar r1; al hacerlo queda "[borrado]" pero
# su hija sigue en el árbol.
def test_arbol_respuestas_ordenado_y_borrado(ctx):
    c, _, usuario = ctx
    a, b = usuario("ana"), usuario("beto")
    hid = c.post("/hilos", json={"titulo": "Pregunta", "texto": "?"}, headers=a).json()["id"]
    r1 = c.post(f"/hilos/{hid}/respuestas", json={"texto": "primera"}, headers=b).json()["id"]
    r2 = c.post(f"/hilos/{hid}/respuestas", json={"texto": "segunda"}, headers=a).json()["id"]
    c.post(f"/hilos/{hid}/respuestas", json={"texto": "hija", "padre_id": r1}, headers=a)
    c.post("/votos", json={"tipo": "respuesta", "id": r2, "valor": 1}, headers=b)
    arbol = c.get(f"/hilos/{hid}").json()["arbol"]
    assert [n["texto"] for n in arbol] == ["segunda", "primera"]  # más votada primero
    assert arbol[1]["hijos"][0]["texto"] == "hija"
    assert c.delete(f"/respuestas/{r1}", headers=a).status_code == 403
    c.delete(f"/respuestas/{r1}", headers=b)
    arbol = c.get(f"/hilos/{hid}").json()["arbol"]
    assert arbol[1]["texto"] == "[borrado]" and arbol[1]["hijos"][0]["texto"] == "hija"


# La respuesta r es del hilo 1: usarla como padre en el hilo 2 => 422.
def test_padre_de_otro_hilo(ctx):
    c, _, usuario = ctx
    a = usuario("ana")
    h1 = c.post("/hilos", json={"titulo": "Uno", "texto": "."}, headers=a).json()["id"]
    h2 = c.post("/hilos", json={"titulo": "Dos", "texto": "."}, headers=a).json()["id"]
    r = c.post(f"/hilos/{h1}/respuestas", json={"texto": "x"}, headers=a).json()["id"]
    assert c.post(f"/hilos/{h2}/respuestas", json={"texto": "y", "padre_id": r}, headers=a).status_code == 422


# "Viejo" tiene 1 voto y 3 días más: gana en "top". "Nuevo" gana en
# "nuevos" y en "populares" (3 días = 259200 / 45000 = 5,76 puntos de
# juventud contra 0 por tener un solo voto, log10(1) = 0).
def test_orden_listado_y_borrado_hilo(ctx):
    c, reloj, usuario = ctx
    a, b = usuario("ana"), usuario("beto")
    viejo = c.post("/hilos", json={"titulo": "Viejo", "texto": "."}, headers=a).json()["id"]
    c.post("/votos", json={"tipo": "hilo", "id": viejo, "valor": 1}, headers=b)
    reloj.t += 3 * 86400
    nuevo = c.post("/hilos", json={"titulo": "Nuevo", "texto": "."}, headers=a).json()["id"]
    assert [h["id"] for h in c.get("/hilos?orden=top").json()] == [viejo, nuevo]
    assert [h["id"] for h in c.get("/hilos?orden=nuevos").json()] == [nuevo, viejo]
    assert c.get("/hilos?orden=populares").json()[0]["id"] == nuevo
    assert c.get("/hilos?orden=raro").status_code == 422
    assert c.delete(f"/hilos/{viejo}", headers=b).status_code == 403
    assert c.delete(f"/hilos/{viejo}", headers=a).status_code == 204
    assert c.get(f"/hilos/{viejo}").status_code == 404
