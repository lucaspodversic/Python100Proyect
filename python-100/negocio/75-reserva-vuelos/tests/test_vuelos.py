"""Tests de la reserva de vuelos: búsqueda, asientos, expiración, precios y concurrencia."""
from __future__ import annotations

import threading
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import servicio
from app.main import crear_app
from app.modelos import Usuario

ADMIN = ("admin@vuelos.local", "clave-admin-123")


class Reloj:
    """Reloj controlable: los tests avanzan el tiempo a voluntad."""

    def __init__(self) -> None:
        """Empieza el 1/3/2026 a las 12:00, nueve días antes del vuelo de prueba."""
        self.t = datetime(2026, 3, 1, 12, 0)

    def __call__(self) -> datetime:
        """Devuelve la hora simulada."""
        return self.t

    def avanzar(self, minutos: int) -> None:
        """Adelanta el reloj ``minutos`` (para hacer vencer retenciones)."""
        self.t += timedelta(minutes=minutos)


def login(c, email, pw="secreta123"):
    """Cabecera Authorization para el usuario."""
    return {"Authorization": "Bearer " + c.post("/auth/login", json={"email": email, "password": pw}).json()["token"]}


@pytest.fixture()
def reloj():
    """Un reloj nuevo por test."""
    return Reloj()


@pytest.fixture()
def app(tmp_path, reloj):
    """App con base nueva en tmp_path y el reloj simulado."""
    return crear_app(f"sqlite:///{tmp_path / 'v.db'}", *ADMIN, reloj=reloj)


@pytest.fixture()
def c(app):
    """Cliente HTTP de pruebas."""
    return TestClient(app)


@pytest.fixture()
def vuelo(c):
    """Vuelo EZE→MDZ del 10/3/2026 con 2 filas × columnas AB = 4 asientos y precio base de
    $1000 (100 000 centavos).
    """
    r = c.post("/vuelos", headers=login(c, *ADMIN), json={
        "codigo": "AR1302", "origen": "EZE", "destino": "MDZ", "salida": "2026-03-10T09:30:00",
        "filas": 2, "columnas": "AB", "precio_base_centavos": 100_000})
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture()
def cliente(c):
    """Fábrica de clientes: registra un email y devuelve su cabecera."""
    def _crear(email="ana@x.com"):
        """Registra y loguea un cliente."""
        c.post("/auth/registro", json={"email": email, "nombre": "x", "password": "secreta123"})
        return login(c, email)
    return _crear


def test_busqueda_y_validacion(c, vuelo):
    """La búsqueda no distingue mayúsculas en los códigos IATA; con 0 % de ocupación el precio
    es el base y hay 4 asientos libres. Otra fecha no da resultados y origen = destino
    es inválido.
    """
    r = c.get("/vuelos/buscar", params={"origen": "eze", "destino": "MDZ", "fecha": "2026-03-10"}).json()
    assert len(r) == 1 and r[0]["asientos_libres"] == 4 and r[0]["precio_centavos"] == 100_000
    assert c.get("/vuelos/buscar", params={"origen": "EZE", "destino": "MDZ", "fecha": "2026-03-11"}).json() == []
    admin = login(c, *ADMIN)
    assert c.post("/vuelos", headers=admin, json={"codigo": "AR1", "origen": "EZE", "destino": "EZE",
                  "salida": "2026-03-10T09:30:00", "filas": 1, "columnas": "A", "precio_base_centavos": 1}).status_code == 400


def test_retener_confirmar_y_doble_venta(c, vuelo, cliente):
    """El asiento se normaliza a mayúsculas ('1a' → '1A'). Mientras está retenido nadie más
    puede tomarlo (409) y figura ocupado. Confirmar una reserva ajena da 404 (no se
    revela su existencia).
    """
    ana, bob = cliente("ana@x.com"), cliente("bob@x.com")
    r = c.post("/reservas", headers=ana, json={"vuelo_id": vuelo, "asiento": "1a", "pasajero": "Ana"})
    assert r.status_code == 201 and r.json()["asiento"] == "1A" and r.json()["estado"] == "retenida"
    pnr = r.json()["pnr"]
    assert c.post("/reservas", headers=bob, json={"vuelo_id": vuelo, "asiento": "1A", "pasajero": "Bob"}).status_code == 409
    assert c.get(f"/vuelos/{vuelo}/asientos").json()["1A"] is False
    # Bob no puede confirmar la reserva de Ana.
    assert c.post(f"/reservas/{pnr}/confirmar", headers=bob).status_code == 404
    assert c.post(f"/reservas/{pnr}/confirmar", headers=ana).json()["estado"] == "confirmada"


def test_asiento_invalido(c, vuelo, cliente):
    """Fila 9 o columna Z fuera del avión y formatos inválidos → 400; vuelo inexistente → 404."""
    ana = cliente()
    assert c.post("/reservas", headers=ana, json={"vuelo_id": vuelo, "asiento": "9Z", "pasajero": "A"}).status_code == 400
    assert c.post("/reservas", headers=ana, json={"vuelo_id": vuelo, "asiento": "xx", "pasajero": "A"}).status_code == 400
    assert c.post("/reservas", headers=ana, json={"vuelo_id": 99, "asiento": "1A", "pasajero": "A"}).status_code == 404


def test_retencion_expira_y_libera(c, vuelo, cliente, reloj):
    """Pasada la ventana de retención (+1 minuto) ya no se puede confirmar, la reserva figura
    como expirada y el asiento queda libre para otro.
    """
    ana, bob = cliente("ana@x.com"), cliente("bob@x.com")
    pnr = c.post("/reservas", headers=ana, json={"vuelo_id": vuelo, "asiento": "2B", "pasajero": "Ana"}).json()["pnr"]
    reloj.avanzar(servicio.MINUTOS_RETENCION + 1)
    assert c.post(f"/reservas/{pnr}/confirmar", headers=ana).status_code == 409
    assert c.get("/reservas", headers=ana).json()[0]["estado"] == "expirada"
    # El asiento volvió a estar libre para otro cliente.
    assert c.post("/reservas", headers=bob, json={"vuelo_id": vuelo, "asiento": "2B", "pasajero": "Bob"}).status_code == 201


def test_precio_dinamico_y_cancelacion(c, vuelo, cliente):
    """Recargo = 50 % × ocupación previa: 0/4 → +0 %, 1/4 → +12,5 %, 2/4 → +25 %. Cancelar
    libera el asiento y cancelar dos veces es un conflicto.
    """
    ana = cliente()
    precios = []
    pnrs = []
    for asiento in ("1A", "1B", "2A"):
        r = c.post("/reservas", headers=ana, json={"vuelo_id": vuelo, "asiento": asiento, "pasajero": "A"}).json()
        precios.append(r["precio_centavos"])
        pnrs.append(r["pnr"])
    # 0 %, 25 % y 50 % de ocupación previa -> +0 %, +12,5 %, +25 %.
    assert precios == [100_000, 112_500, 125_000]
    assert c.post(f"/reservas/{pnrs[0]}/cancelar", headers=ana).json()["estado"] == "cancelada"
    assert c.post(f"/reservas/{pnrs[0]}/cancelar", headers=ana).status_code == 409
    assert c.get(f"/vuelos/{vuelo}/asientos").json()["1A"] is True


def test_vuelo_ya_salido(c, vuelo, cliente, reloj):
    """El 11/3 el vuelo del 10/3 ya salió: no se puede reservar."""
    reloj.t = datetime(2026, 3, 11)
    assert c.post("/reservas", headers=cliente(), json={"vuelo_id": vuelo, "asiento": "1A", "pasajero": "A"}).status_code == 400


def test_concurrencia_mismo_asiento(app, vuelo, cliente):
    """10 hilos intentan retener 1A a la vez (sincronizados con una barrera): con BEGIN
    IMMEDIATE gana exactamente uno y los otros 9 reciben 409.
    """
    cliente()  # usuario id 2
    fabrica = app.state.fabrica
    ganadores, perdedores = [], []
    barrera = threading.Barrier(10)

    def intentar() -> None:
        """Espera a todos y prueba retener en su propia transacción; anota si ganó o el código
        de error.
        """
        barrera.wait()
        try:
            with fabrica.begin() as s:
                servicio.retener(s, s.get(Usuario, 2), vuelo, "1A", "X", datetime(2026, 3, 1))
            ganadores.append(1)
        except servicio.ErrorNegocio as e:
            perdedores.append(e.codigo)

    hilos = [threading.Thread(target=intentar) for _ in range(10)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert len(ganadores) == 1 and perdedores == [409] * 9
