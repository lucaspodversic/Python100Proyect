"""Tests end-to-end de la plataforma de cursos."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import crear_app
from app import servicio

ADMIN = ("admin@cursos.local", "clave-admin-123")
PREGUNTAS = [
    {"enunciado": "2+2", "opciones": ["3", "4"], "correcta": 1},
    {"enunciado": "Capital de Argentina", "opciones": ["Córdoba", "Buenos Aires", "Rosario"], "correcta": 1},
]


def login(c, email, pw="secreta123"):
    """Inicia sesión y devuelve la cabecera Authorization lista para usar."""
    return {"Authorization": "Bearer " + c.post("/auth/login", json={"email": email, "password": pw}).json()["token"]}


def registrar(c, email):
    """Registra un usuario (queda como alumno) y devuelve su id."""
    return c.post("/auth/registro", json={"email": email, "nombre": email, "password": "secreta123"}).json()["id"]


@pytest.fixture()
def c(tmp_path):
    """Cliente de pruebas con una base SQLite nueva en tmp_path para cada test, así no
    comparten estado.
    """
    return TestClient(crear_app(f"sqlite:///{tmp_path / 'c.db'}", *ADMIN))


@pytest.fixture()
def actores(c):
    """Crea admin, profesor y alumno; devuelve sus cabeceras."""
    admin = login(c, *ADMIN)
    uid = registrar(c, "profe@x.com")
    c.patch(f"/usuarios/{uid}/rol", headers=admin, json={"rol": "profesor"})
    registrar(c, "alu@x.com")
    return {"admin": admin, "profe": login(c, "profe@x.com"), "alu": login(c, "alu@x.com")}


@pytest.fixture()
def curso(c, actores):
    """Curso del profesor con 2 lecciones y un examen de 2 preguntas con 2 intentos (nota
    mínima 60 por defecto). Todavía sin publicar.
    """
    p = actores["profe"]
    cid = c.post("/cursos", headers=p, json={"titulo": "Python 101"}).json()["id"]
    for i in (1, 2):
        assert c.post(f"/cursos/{cid}/lecciones", headers=p, json={"orden": i, "titulo": f"L{i}", "contenido": "..."}).status_code == 201
    assert c.put(f"/cursos/{cid}/examen", headers=p, json={"preguntas": PREGUNTAS, "max_intentos": 2}).status_code == 200
    return cid


def test_alumno_no_crea_cursos(c, actores):
    """Crear cursos exige rol profesor: 403 para un alumno."""
    assert c.post("/cursos", headers=actores["alu"], json={"titulo": "Hack"}).status_code == 403


def test_publicacion_requiere_lecciones_y_autoria(c, actores):
    """Un curso sin lecciones no se publica (400) y otro profesor no puede agregar lecciones a
    un curso ajeno (403).
    """
    p = actores["profe"]
    cid = c.post("/cursos", headers=p, json={"titulo": "Vacío"}).json()["id"]
    assert c.post(f"/cursos/{cid}/publicar", headers=p).status_code == 400
    # Otro profesor no puede tocar el curso ajeno.
    uid = registrar(c, "otro@x.com")
    c.patch(f"/usuarios/{uid}/rol", headers=actores["admin"], json={"rol": "profesor"})
    assert c.post(f"/cursos/{cid}/lecciones", headers=login(c, "otro@x.com"),
                  json={"orden": 1, "titulo": "x", "contenido": "x"}).status_code == 403


def test_orden_de_leccion_unico_y_examen_invalido(c, actores, curso):
    """Orden 1 repetido → 409; una pregunta con una sola opción no es válida → 400."""
    p = actores["profe"]
    assert c.post(f"/cursos/{curso}/lecciones", headers=p, json={"orden": 1, "titulo": "x", "contenido": "x"}).status_code == 409
    malo = [{"enunciado": "x", "opciones": ["a"], "correcta": 0}]
    assert c.put(f"/cursos/{curso}/examen", headers=p, json={"preguntas": malo}).status_code == 400


def test_flujo_completo_alumno(c, actores, curso):
    """Recorre el flujo entero: sin publicar no aparece en el catálogo; sin inscripción no se
    ven las lecciones; la doble inscripción da 409; el examen no expone las respuestas;
    completar es idempotente; con 100 % de lecciones pero sin examen todavía no hay
    certificado. Nota: 1 de 2 aciertos = 50 < 60, desaprobado; 2 de 2 = 100, aprobado;
    después de aprobar no se puede volver a rendir (409).
    """
    a, p = actores["alu"], actores["profe"]
    # Antes de publicar no aparece ni admite inscripción.
    assert c.get("/cursos").json() == []
    assert c.post(f"/cursos/{curso}/inscripcion", headers=a).status_code == 404
    c.post(f"/cursos/{curso}/publicar", headers=p)
    assert len(c.get("/cursos").json()) == 1
    # Sin inscripción no se ven las lecciones.
    assert c.get(f"/cursos/{curso}/lecciones", headers=a).status_code == 403
    assert c.post(f"/cursos/{curso}/inscripcion", headers=a).status_code == 201
    assert c.post(f"/cursos/{curso}/inscripcion", headers=a).status_code == 409
    lecciones = c.get(f"/cursos/{curso}/lecciones", headers=a).json()
    # El examen no expone la respuesta correcta.
    examen = c.get(f"/cursos/{curso}/examen", headers=a).json()
    assert "correcta" not in examen["preguntas"][0]
    for l in lecciones:
        c.post(f"/lecciones/{l['id']}/completar", headers=a)
    c.post(f"/lecciones/{lecciones[0]['id']}/completar", headers=a)  # idempotente
    prog = c.get(f"/cursos/{curso}/progreso", headers=a).json()
    assert prog["porcentaje"] == 100 and not prog["certificado"]
    # Primer intento: 1 de 2 = 50 % < 60 % -> desaprobado.
    assert c.post(f"/cursos/{curso}/examen/intentos", headers=a, json={"respuestas": [1, 0]}).json() == {"nota": 50, "aprobado": False}
    assert c.post(f"/cursos/{curso}/examen/intentos", headers=a, json={"respuestas": [1, 1]}).json()["aprobado"] is True
    assert c.post(f"/cursos/{curso}/examen/intentos", headers=a, json={"respuestas": [1, 1]}).status_code == 409
    assert c.get(f"/cursos/{curso}/progreso", headers=a).json()["certificado"] is True
    assert c.get(f"/cursos/{curso}/inscriptos", headers=p).json()["inscriptos"] == 1


def test_maximo_de_intentos(c, actores, curso):
    """max_intentos = 2: dos intentos fallidos se aceptan (201) y el tercero se rechaza aunque
    fuera correcto o incompleto (409, el límite se controla antes que el contenido).
    """
    a = actores["alu"]
    c.post(f"/cursos/{curso}/publicar", headers=actores["profe"])
    c.post(f"/cursos/{curso}/inscripcion", headers=a)
    for _ in range(2):
        assert c.post(f"/cursos/{curso}/examen/intentos", headers=a, json={"respuestas": [0, 0]}).status_code == 201
    assert c.post(f"/cursos/{curso}/examen/intentos", headers=a, json={"respuestas": [1, 1]}).status_code == 409
    assert c.post(f"/cursos/{curso}/examen/intentos", headers=a, json={"respuestas": [1]}).status_code == 409


def test_corregir_unitario():
    """2/2 = 100. Con 3 preguntas y 1 acierto: 100 // 3 = 33 (redondeo hacia abajo, así nunca
    se aprueba de más). Cantidad de respuestas distinta a la de preguntas → error.
    """
    assert servicio.corregir(PREGUNTAS, [1, 1]) == 100
    assert servicio.corregir(PREGUNTAS + PREGUNTAS[:1], [1, 0, 0]) == 33
    with pytest.raises(servicio.ErrorNegocio):
        servicio.corregir(PREGUNTAS, [1])
