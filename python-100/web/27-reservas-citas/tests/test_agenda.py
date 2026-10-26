"""Tests del motor de agenda y de la API."""
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from reservas.agenda import Agenda, ErrorAgenda, Franja, solapan
from reservas.app import crear_app

# AHORA es el día anterior, así la anticipación de 60 min no afecta al lunes.
LUNES = date(2026, 11, 2)  # es lunes
AHORA = datetime(2026, 11, 1, 10, 0)  # domingo anterior


@pytest.fixture()
# Franjas cortas de 1 hora para que las listas esperadas sean chicas.
def ag():
    return Agenda({"ana": {0: ["09:00-10:00", "15:00-16:00"]}}, {"corte": 30, "color": 90},
                  paso_min=15, anticipacion_min=60, reloj=lambda: AHORA)


# 9-10 y 10-11 son contiguos (no se solapan); 9-11 y 10-11 sí.
def test_franja_y_solapamiento():
    assert Franja.parse("09:00-10:00").hasta.hour == 10
    with pytest.raises(ValueError):
        Franja.parse("10:00-09:00")
    a, b, c = datetime(2026, 1, 1, 9), datetime(2026, 1, 1, 10), datetime(2026, 1, 1, 11)
    assert not solapan(a, b, b, c)  # contiguos no se solapan
    assert solapan(a, c, b, c)


def test_huecos_respetan_duracion_y_franjas(ag):
    h = [x.strftime("%H:%M") for x in ag.disponibles("ana", "corte", LUNES)]
    # Corte = 30 min, grilla de 15: en 9-10 entran 9:00, 9:15 y 9:30
    # (9:45 terminaría 10:15, fuera de la franja). Igual en 15-16.
    assert h == ["09:00", "09:15", "09:30", "15:00", "15:15", "15:30"]
    assert ag.disponibles("ana", "color", LUNES) == []  # 90 min no entra en franjas de 60
    assert ag.disponibles("ana", "corte", date(2026, 11, 3)) == []  # martes no atiende


def test_reserva_bloquea_solapados(ag):
    ag.reservar("ana", "corte", datetime(2026, 11, 2, 9, 15), "Lucas", "l@x.com")
    # Turno 9:15-9:45 ocupado: 9:00-9:30 y 9:30-10:00 se pisan con él, así que
    # de la mañana no queda nada.
    h = [x.strftime("%H:%M") for x in ag.disponibles("ana", "corte", LUNES)]
    assert h == ["15:00", "15:15", "15:30"]  # 9:00 y 9:30 se solapan con 9:15-9:45
    with pytest.raises(ErrorAgenda) as e:
        ag.reservar("ana", "corte", datetime(2026, 11, 2, 9, 15), "Otro", "o@x.com")
    assert e.value.codigo == 409


# Ahora = 9:40 del mismo lunes => límite 10:40. La grilla desde 9:00 de a
# 15 min da 10:30 (antes del límite) y 10:45 (primer turno válido).
def test_no_reserva_en_el_pasado_ni_sin_anticipacion():
    ag = Agenda({"ana": {0: ["09:00-12:00"]}}, {"corte": 30}, reloj=lambda: datetime(2026, 11, 2, 9, 40))
    h = [x.strftime("%H:%M") for x in ag.disponibles("ana", "corte", LUNES)]
    assert h[0] == "10:45"  # 9:40 + 60 min de anticipación -> primer paso de grilla libre


# Código falso => error; código correcto => libera 15:00; cancelar de
# nuevo => 409 porque ya no está activa.
def test_cancelar_libera_horario(ag):
    r = ag.reservar("ana", "corte", datetime(2026, 11, 2, 15, 0), "Lucas", "l@x.com")
    with pytest.raises(ErrorAgenda):
        ag.cancelar(r["id"], "codigo-falso")
    ag.cancelar(r["id"], r["codigo_cancelacion"])
    assert datetime(2026, 11, 2, 15, 0) in ag.disponibles("ana", "corte", LUNES)
    with pytest.raises(ErrorAgenda):
        ag.cancelar(r["id"], r["codigo_cancelacion"])


# Profesional inexistente y email sin "@".
def test_validaciones(ag):
    with pytest.raises(ErrorAgenda):
        ag.disponibles("nadie", "corte", LUNES)
    with pytest.raises(ErrorAgenda):
        ag.reservar("ana", "corte", datetime(2026, 11, 2, 9), "Lucas", "sin-arroba")


# Mismo turno dos veces => 409; la agenda sin token => 401, con token
# muestra a Lucas; y la cancelación por API funciona con el código devuelto.
def test_api(ag):
    c = TestClient(crear_app(ag, token_admin="adm"))
    assert c.get("/profesionales/ana/disponibles", params={"servicio": "corte", "dia": "2026-11-02"}).json()[0] == "09:00"
    r = c.post("/reservas", json={"profesional": "ana", "servicio": "corte", "inicio": "2026-11-02T09:00:00",
                                  "cliente": "Lucas", "email": "l@x.com"})
    assert r.status_code == 201
    assert c.post("/reservas", json={"profesional": "ana", "servicio": "corte", "inicio": "2026-11-02T09:00:00",
                                     "cliente": "X", "email": "x@x.com"}).status_code == 409
    assert c.get("/profesionales/ana/agenda", params={"dia": "2026-11-02"}).status_code == 401
    agenda = c.get("/profesionales/ana/agenda", params={"dia": "2026-11-02"}, headers={"X-Admin-Token": "adm"}).json()
    assert agenda[0]["cliente"] == "Lucas"
    rid, cod = r.json()["id"], r.json()["codigo_cancelacion"]
    assert c.post(f"/reservas/{rid}/cancelar", json={"codigo": cod}).json() == {"estado": "cancelada"}
