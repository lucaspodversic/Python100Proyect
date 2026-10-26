"""Tests de la mesa de ayuda."""
from __future__ import annotations

import threading
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import servicio
from app.main import crear_app
from app.modelos import Estado, Prioridad, Usuario

ADMIN = ("admin@soporte.local", "clave-admin-123")


class Reloj:
    """Reloj controlable: empieza el 1/6/2026 a las 9:00 y los tests lo avanzan a mano."""
    def __init__(self):
        """Hora inicial fija."""
        self.t = datetime(2026, 6, 1, 9, 0)

    def __call__(self):
        """Devuelve la hora 'actual' simulada."""
        return self.t


@pytest.fixture()
def reloj():
    """Un reloj nuevo por test."""
    return Reloj()


@pytest.fixture()
def app(tmp_path, reloj):
    """App con una base nueva en tmp_path y el reloj simulado."""
    return crear_app(f"sqlite:///{tmp_path / 't.db'}", *ADMIN, reloj=reloj)


@pytest.fixture()
def c(app):
    """Cliente HTTP de pruebas."""
    return TestClient(app)


def login(c, email, pw="secreta123"):
    """Cabecera Authorization para el usuario."""
    return {"Authorization": "Bearer " + c.post("/auth/login", json={"email": email, "password": pw}).json()["token"]}


def alta(c, email, rol=None):
    """Registra un usuario, opcionalmente le cambia el rol vía admin, y devuelve (cabecera,
    id).
    """
    uid = c.post("/auth/registro", json={"email": email, "nombre": email[:3], "password": "secreta123"}).json()["id"]
    if rol:
        c.patch(f"/usuarios/{uid}/rol", headers=login(c, *ADMIN), json={"rol": rol})
    return login(c, email), uid


@pytest.fixture()
def gente(c):
    """Un cliente y dos agentes (ag1 se registra primero, así gana los empates de carga)."""
    cli, _ = alta(c, "cli@x.com")
    ag1, id1 = alta(c, "ag1@x.com", "agente")
    ag2, id2 = alta(c, "ag2@x.com", "agente")
    return {"cli": cli, "ag1": ag1, "ag2": ag2, "id1": id1, "id2": id2}


def test_sla_y_asignacion_balanceada(c, gente, reloj):
    """Urgente creado a las 9:00 → vence la respuesta a las 10:00 (SLA 1 h). A las 11:00 está
    incumplido y la respuesta tardía queda marcada. Subir la baja a alta recalcula desde
    la creación: 9:00 + 4 h = 13:00. El cliente no puede ver el reporte de incumplidos
    (403).
    """
    t1 = c.post("/tickets", headers=gente["cli"], json={"asunto": "No anda", "descripcion": "x", "prioridad": "urgente"}).json()
    t2 = c.post("/tickets", headers=gente["cli"], json={"asunto": "Consulta", "descripcion": "y", "prioridad": "baja"}).json()
    # Reparto por carga: el primero a ag1, el segundo a ag2.
    assert (t1["agente_id"], t2["agente_id"]) == (gente["id1"], gente["id2"])
    assert t1["vence_respuesta"] == "2026-06-01T10:00:00"
    reloj.t += timedelta(hours=2)
    assert c.get("/tickets/incumplidos", headers=gente["ag1"]).json() == [t1["id"]]
    # La respuesta tardía queda registrada como incumplida.
    r = c.post(f"/tickets/{t1['id']}/comentarios", headers=gente["ag1"], json={"texto": "Mirando"}).json()
    assert r["sla"]["respuesta_incumplida"] is True
    # Subir prioridad del segundo recalcula plazos.
    r = c.post(f"/tickets/{t2['id']}/prioridad", headers=gente["ag2"], json={"prioridad": "alta"}).json()
    assert r["vence_respuesta"] == "2026-06-01T13:00:00"
    assert c.get("/tickets/incumplidos", headers=gente["cli"]).status_code == 403


def test_maquina_de_estados(c, gente, reloj):
    """Transiciones inválidas (409), por rol (403) y por asignación (403). Que el cliente
    comente en 'esperando_cliente' devuelve el ticket a 'en_progreso'. 8 días después de
    resuelto ya pasó el plazo de reapertura (7 días), pero el cliente sí puede cerrarlo;
    un ticket cerrado no admite comentarios.
    """
    tid = c.post("/tickets", headers=gente["cli"], json={"asunto": "Error", "descripcion": "x"}).json()["id"]
    paso = lambda h, e: c.post(f"/tickets/{tid}/estado", headers=gente[h], json={"estado": e})  # noqa: E731
    assert paso("ag1", "resuelto").status_code == 409            # abierto → resuelto no existe
    assert paso("cli", "en_progreso").status_code == 403         # cliente no puede empezar
    assert paso("ag2", "en_progreso").status_code == 403         # está asignado a ag1
    assert paso("ag1", "en_progreso").json()["estado"] == "en_progreso"
    assert paso("ag1", "esperando_cliente").status_code == 200
    # Cuando el cliente responde, vuelve solo a "en progreso".
    r = c.post(f"/tickets/{tid}/comentarios", headers=gente["cli"], json={"texto": "Adjunto captura"}).json()
    assert r["estado"] == "en_progreso"
    assert paso("ag1", "resuelto").status_code == 200
    reloj.t += timedelta(days=8)
    assert paso("cli", "abierto").status_code == 409             # fuera de plazo de reapertura
    assert paso("cli", "cerrado").json()["estado"] == "cerrado"
    assert c.post(f"/tickets/{tid}/comentarios", headers=gente["cli"], json={"texto": "?"}).status_code == 409


def test_reapertura_en_plazo(c, gente):
    """Recién resuelto (dentro de los 7 días) el cliente puede reabrirlo."""
    tid = c.post("/tickets", headers=gente["cli"], json={"asunto": "Error", "descripcion": "x"}).json()["id"]
    for e in ("en_progreso", "resuelto"):
        c.post(f"/tickets/{tid}/estado", headers=gente["ag1"], json={"estado": e})
    assert c.post(f"/tickets/{tid}/estado", headers=gente["cli"], json={"estado": "abierto"}).json()["estado"] == "abierto"


def test_notas_internas_y_privacidad(c, gente):
    """El cliente ve solo el comentario público; otro agente ve los 2. El cliente no puede
    crear notas internas. Un tercero no ve el ticket (404) ni lo lista, y un agente no
    puede abrir tickets como cliente.
    """
    tid = c.post("/tickets", headers=gente["cli"], json={"asunto": "Factura", "descripcion": "x"}).json()["id"]
    c.post(f"/tickets/{tid}/comentarios", headers=gente["ag1"], json={"texto": "cliente moroso", "interno": True})
    c.post(f"/tickets/{tid}/comentarios", headers=gente["ag1"], json={"texto": "Hola!"})
    assert [x["texto"] for x in c.get(f"/tickets/{tid}", headers=gente["cli"]).json()["comentarios"]] == ["Hola!"]
    assert len(c.get(f"/tickets/{tid}", headers=gente["ag2"]).json()["comentarios"]) == 2
    assert c.post(f"/tickets/{tid}/comentarios", headers=gente["cli"], json={"texto": "x", "interno": True}).status_code == 403
    otro, _ = alta(c, "otro@x.com")
    assert c.get(f"/tickets/{tid}", headers=otro).status_code == 404
    assert c.get("/tickets", headers=otro).json() == []
    assert c.post("/tickets", headers=gente["ag1"], json={"asunto": "abc", "descripcion": "x"}).status_code == 403


def test_tomar_concurrente(app, gente):
    """6 hilos (3 por agente) intentan tomar el mismo ticket sin asignar a la vez,
    sincronizados con una barrera. El UPDATE condicional dentro de BEGIN IMMEDIATE deja
    exactamente un ganador.
    """
    with app.state.fabrica.begin() as s:
        cli = s.get(Usuario, 2)
        tid = servicio.crear_ticket(s, cli, "Sin asignar", "x", Prioridad.MEDIA, datetime(2026, 1, 1),
                                    autoasignar=False).id
    ganadores = []
    barrera = threading.Barrier(6)

    def intentar(uid):
        """Espera a los demás hilos y prueba tomar el ticket en su propia transacción."""
        barrera.wait()
        with app.state.fabrica.begin() as s:
            if servicio.tomar(s, tid, s.get(Usuario, uid)):
                ganadores.append(uid)

    hilos = [threading.Thread(target=intentar, args=(gente["id1"] if i % 2 else gente["id2"],)) for i in range(6)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert len(ganadores) == 1


def test_unidad_sla():
    """Media: respuesta en 8 h y resolución en 3 días, en horas corridas. No existe la
    transición cerrado → abierto.
    """
    vr, vf = servicio.plazos(Prioridad.MEDIA, datetime(2026, 1, 1))
    assert vr == datetime(2026, 1, 1, 8) and vf == datetime(2026, 1, 4)
    assert (Estado.CERRADO, Estado.ABIERTO) not in servicio.TRANSICIONES  # cerrado es final
