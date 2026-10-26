"""Tests de WebSockets con el TestClient de Starlette (sin servidor real)."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from chat.app import crear_app
from chat.salas import GestorSalas


@pytest.fixture()
# El TestClient de Starlette soporta WebSockets en memoria, sin abrir puertos.
def cliente():
    return TestClient(crear_app())


# Secuencia de mensajes al conectar: historial y luego aviso de entrada.
# Por eso cada conexión consume dos mensajes antes de la prueba en sí.
def test_mensaje_llega_a_todos(cliente):
    with cliente.websocket_connect("/ws/general?usuario=ana") as a:
        assert a.receive_json()["tipo"] == "historial"
        a.receive_json()  # aviso "ana entró"
        with cliente.websocket_connect("/ws/general?usuario=beto") as b:
            b.receive_json()  # historial
            assert "beto entró" in a.receive_json()["texto"]
            b.receive_json()  # su propio aviso de entrada
            # El mensaje de beto debe llegarle a ana y también al propio beto.
            b.send_json({"texto": "hola ana"})
            for ws in (a, b):
                m = ws.receive_json()
                assert m["tipo"] == "mensaje" and m["usuario"] == "beto" and m["texto"] == "hola ana"


# caro entra después del mensaje de ana y lo recibe en el historial inicial.
def test_historial_para_quien_entra_despues(cliente):
    with cliente.websocket_connect("/ws/sala1?usuario=ana") as a:
        a.receive_json(); a.receive_json()
        a.send_json({"texto": "primer mensaje"})
        a.receive_json()
        with cliente.websocket_connect("/ws/sala1?usuario=caro") as c:
            hist = c.receive_json()
            assert [m["texto"] for m in hist["mensajes"]] == ["primer mensaje"]


# Si b hubiera recibido el mensaje de a, su próximo receive sería "solo en a".
def test_salas_aisladas(cliente):
    with cliente.websocket_connect("/ws/a?usuario=u1") as a, cliente.websocket_connect("/ws/b?usuario=u2") as b:
        a.receive_json(); a.receive_json(); b.receive_json(); b.receive_json()
        a.send_json({"texto": "solo en a"})
        assert a.receive_json()["texto"] == "solo en a"
        b.send_json({"texto": "solo en b"})
        assert b.receive_json()["texto"] == "solo en b"  # b no recibió el de a


# Tres errores distintos: no-JSON, texto vacío y 2000 caracteres (> 1000).
def test_errores_de_formato(cliente):
    with cliente.websocket_connect("/ws/general?usuario=ana") as a:
        a.receive_json(); a.receive_json()
        a.send_text("esto no es json")
        assert a.receive_json()["tipo"] == "error"
        a.send_json({"texto": "   "})
        assert a.receive_json()["texto"] == "Mensaje vacío"
        a.send_json({"texto": "x" * 2000})
        assert "largo" in a.receive_json()["texto"]


# "<script>" no cumple PATRON_NOMBRE: se cierra con 1008 sin aceptar.
def test_nombre_invalido_rechazado(cliente):
    with pytest.raises(WebSocketDisconnect) as e:
        with cliente.websocket_connect("/ws/general?usuario=<script>") as ws:
            ws.receive_json()
    assert e.value.code == 1008


# Segundo "ana" en la misma sala: recibe error y se cierra.
def test_nombre_duplicado(cliente):
    with cliente.websocket_connect("/ws/general?usuario=ana") as a:
        a.receive_json(); a.receive_json()
        with cliente.websocket_connect("/ws/general?usuario=ana") as dup:
            assert dup.receive_json()["tipo"] == "error"


def test_endpoints_rest_y_salida(cliente):
    with cliente.websocket_connect("/ws/general?usuario=ana") as a:
        a.receive_json(); a.receive_json()
        with cliente.websocket_connect("/ws/general?usuario=beto") as b:
            b.receive_json(); b.receive_json(); a.receive_json()
            assert cliente.get("/salas/general/usuarios").json() == ["ana", "beto"]
            assert cliente.get("/salas").json() == [{"sala": "general", "conectados": 2}]
        # Al salir del bloque `with` de beto, ana recibe el aviso de salida.
        salida = a.receive_json()
        assert "beto salió" in salida["texto"] and salida["usuarios"] == ["ana"]


def test_html_cliente(cliente):
    assert "WebSocket" in cliente.get("/").text


def test_construir_mensaje_unitario():
    assert GestorSalas.construir_mensaje("u", {"texto": " hola "})["texto"] == "hola"
    assert isinstance(GestorSalas.construir_mensaje("u", ["no"]), str)
