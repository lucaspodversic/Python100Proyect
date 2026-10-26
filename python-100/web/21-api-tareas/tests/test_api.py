"""Tests de la API de tareas usando el TestClient de FastAPI (sin red)."""
import pytest
from fastapi.testclient import TestClient

from app.main import crear_app


@pytest.fixture()
def cliente() -> TestClient:
    """Cada test arranca con una base SQLite en memoria vacía."""
    return TestClient(crear_app(":memory:"))


# 201 Created y valores por defecto: una tarea nueva arranca pendiente.
def test_crear_y_obtener(cliente):
    r = cliente.post("/tareas", json={"titulo": "Comprar pan", "prioridad": 3})
    assert r.status_code == 201
    tarea = r.json()
    assert tarea["titulo"] == "Comprar pan" and tarea["completada"] is False
    assert cliente.get(f"/tareas/{tarea['id']}").json()["prioridad"] == 3


# 422: título vacío viola min_length=1 y prioridad 9 viola le=3.
def test_validacion_titulo_vacio_y_prioridad(cliente):
    assert cliente.post("/tareas", json={"titulo": ""}).status_code == 422
    assert cliente.post("/tareas", json={"titulo": "x", "prioridad": 9}).status_code == 422


# Dos tareas, una completada: el filtro devuelve solo esa y "libro" solo matchea la primera.
def test_listar_filtrar_y_buscar(cliente):
    cliente.post("/tareas", json={"titulo": "Leer libro"})
    cliente.post("/tareas", json={"titulo": "Pagar luz", "completada": True})
    assert len(cliente.get("/tareas").json()) == 2
    assert [t["titulo"] for t in cliente.get("/tareas?completada=true").json()] == ["Pagar luz"]
    assert len(cliente.get("/tareas", params={"buscar": "libro"}).json()) == 1


# Se insertan en orden 1, 3, 2 para que el orden esperado (3, 2, 1) no
# coincida con el de inserción por casualidad.
def test_orden_por_prioridad_y_paginacion(cliente):
    for p in (1, 3, 2):
        cliente.post("/tareas", json={"titulo": f"p{p}", "prioridad": p})
    titulos = [t["titulo"] for t in cliente.get("/tareas?orden=prioridad").json()]
    assert titulos == ["p3", "p2", "p1"]
    assert len(cliente.get("/tareas?limite=2").json()) == 2
    assert cliente.get("/tareas?orden=DROP").status_code == 422  # orden fuera de lista blanca


# PATCH no debe pisar la descripción; PUT sí reemplaza y guarda la fecha en ISO.
def test_patch_parcial_y_put(cliente):
    t = cliente.post("/tareas", json={"titulo": "A", "descripcion": "desc"}).json()
    r = cliente.patch(f"/tareas/{t['id']}", json={"completada": True})
    assert r.json()["completada"] is True and r.json()["descripcion"] == "desc"
    r = cliente.put(f"/tareas/{t['id']}", json={"titulo": "B", "vence": "2030-01-01"})
    assert r.json()["titulo"] == "B" and r.json()["vence"] == "2030-01-01"


# Borrar dos veces: la segunda ya es 404. PATCH a un id inexistente también.
def test_borrar_y_404(cliente):
    t = cliente.post("/tareas", json={"titulo": "Temporal"}).json()
    assert cliente.delete(f"/tareas/{t['id']}").status_code == 204
    assert cliente.get(f"/tareas/{t['id']}").status_code == 404
    assert cliente.delete(f"/tareas/{t['id']}").status_code == 404
    assert cliente.patch("/tareas/999", json={"titulo": "z"}).status_code == 404


# 2 tareas, 1 completada -> 1 pendiente.
def test_estadisticas(cliente):
    cliente.post("/tareas", json={"titulo": "1"})
    cliente.post("/tareas", json={"titulo": "2", "completada": True})
    assert cliente.get("/estadisticas").json() == {"total": 2, "completadas": 1, "pendientes": 1}


# El texto malicioso se trata como dato: no matchea nada y la tabla sobrevive.
def test_busqueda_no_permite_inyeccion(cliente):
    cliente.post("/tareas", json={"titulo": "segura"})
    r = cliente.get("/tareas", params={"buscar": "'; DROP TABLE tareas; --"})
    assert r.status_code == 200 and r.json() == []
    assert len(cliente.get("/tareas").json()) == 1  # la tabla sigue existiendo


# Dos apps distintas sobre el mismo archivo: la segunda ve lo que creó la primera.
def test_persistencia_en_archivo(tmp_path):
    ruta = str(tmp_path / "tareas.db")
    TestClient(crear_app(ruta)).post("/tareas", json={"titulo": "persistente"})
    assert TestClient(crear_app(ruta)).get("/tareas").json()[0]["titulo"] == "persistente"
