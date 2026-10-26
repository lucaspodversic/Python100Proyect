"""Tests de la API HTTP con TestClient (sin red: todo en memoria)."""
from conftest import ADMIN, H_ADMIN

import pytest

from votacion.api import create_app
from votacion.cliente import Votante
from votacion.cripto import ClavePublica


def clave(cliente) -> ClavePublica:
    """Reconstruye la clave pública desde GET /eleccion (n viaja en hex)."""
    info = cliente.get("/eleccion").json()
    return ClavePublica(int(info["clave_publica"]["n"], 16), info["clave_publica"]["e"])


def test_flujo_http_completo(cliente):
    """Alta en padrón → abrir → firmar → votar → cerrar → resultados y auditoría."""
    r = cliente.post("/eleccion/padron", json={"votante": "ana"}, headers=H_ADMIN)
    assert r.status_code == 201
    token = r.json()["token"]
    assert cliente.post("/eleccion/abrir", headers=H_ADMIN).json()["estado"] == "abierta"

    v = Votante(clave(cliente), "test-2026", "Beto")
    r = cliente.post("/eleccion/firmar", json={"token": token, "cegado": format(v.cegado(), "x")})
    assert r.status_code == 200
    papeleta = v.papeleta(int(r.json()["firma_cegada"], 16))
    r = cliente.post("/eleccion/votar", json=papeleta)
    assert r.status_code == 201 and r.json()["indice"] == 0
    recibo = r.json()["hash"]

    # Mismo token otra vez → 409; misma papeleta otra vez → 409.
    assert cliente.post("/eleccion/firmar", json={"token": token, "cegado": "abc"}).status_code == 409
    assert cliente.post("/eleccion/votar", json=papeleta).status_code == 409

    assert cliente.get("/eleccion/resultados").status_code == 409   # aún abierta
    cierre = cliente.post("/eleccion/cerrar", headers=H_ADMIN).json()
    assert cierre["cabeza"] == recibo                                 # el único bloque es la cabeza
    assert cliente.get("/eleccion/resultados").json()["resultados"] == {"Ana": 0, "Beto": 1, "En blanco": 0}
    aud = cliente.get("/eleccion/auditoria").json()
    assert aud["integra"] and aud["bloques"][0]["hash"] == recibo     # el votante encuentra su recibo


def test_endpoints_admin_protegidos(cliente):
    """Sin header o con uno incorrecto → 401; los endpoints públicos no piden nada."""
    assert cliente.post("/eleccion/padron", json={"votante": "x"}).status_code == 401
    assert cliente.post("/eleccion/abrir", headers={"x-admin-token": "otro"}).status_code == 401
    assert cliente.get("/eleccion").status_code == 200


def test_validacion_pydantic(cliente):
    """Formatos inválidos se rechazan con 422 antes de llegar a la lógica:
    cegado no hexadecimal, serie de largo distinto de 64."""
    cliente.post("/eleccion/abrir", headers=H_ADMIN)
    assert cliente.post("/eleccion/firmar", json={"token": "x" * 20, "cegado": "zz"}).status_code == 422
    assert cliente.post("/eleccion/votar", json={"serie": "ab", "opcion": "Ana", "firma": "1"}).status_code == 422
    # Bien formado pero firma falsa → 403 (lo decide la lógica, no pydantic).
    assert cliente.post("/eleccion/votar", json={"serie": "a" * 64, "opcion": "Ana", "firma": "1f"}).status_code == 403


def test_admin_token_corto_rechazado():
    """Un token de administración de menos de 16 caracteres es un error de configuración."""
    with pytest.raises(ValueError):
        create_app("corto")


def test_app_por_defecto(autoridad):
    """Sin elección inyectada se crea una con opciones por defecto (clave de 2048 bits)."""
    from fastapi.testclient import TestClient
    c = TestClient(create_app(ADMIN, opciones=["Sí", "No"], id_eleccion="consulta"))
    info = c.get("/eleccion").json()
    assert info["opciones"] == ["Sí", "No"] and info["estado"] == "preparacion"
    assert int(info["clave_publica"]["n"], 16).bit_length() == 2048
