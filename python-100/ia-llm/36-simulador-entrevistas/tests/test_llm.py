"""Tests de los adaptadores de LLM SIN red: se usa httpx.MockTransport."""
import json

import httpx
import pytest

from entrevistas.llm import (ErrorLLM, Mensaje, ProveedorAnthropic, ProveedorFalso,
                     ProveedorOpenAI, crear_proveedor)

# Conversación mínima con un mensaje de sistema, para ver cómo lo trata
# cada proveedor.
MSGS = [Mensaje("system", "Sos útil"), Mensaje("user", "Hola")]


def test_openai_formato_y_respuesta(monkeypatch):
    # monkeypatch pone la variable solo durante este test (clave ficticia).
    monkeypatch.setenv("OPENAI_API_KEY", "clave-de-prueba")
    vistos = {}

    # MockTransport llama a esta función en vez de salir a la red: se captura
    # lo que se habría enviado y se devuelve una respuesta armada a mano.
    def manejador(req: httpx.Request) -> httpx.Response:
        vistos["auth"] = req.headers["authorization"]
        vistos["cuerpo"] = json.loads(req.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "¡Hola!"}}]})

    p = ProveedorOpenAI(modelo="m", cliente=httpx.Client(transport=httpx.MockTransport(manejador)))
    assert p.completar(MSGS) == "¡Hola!"
    # La clave salió del entorno y viajó en el header correcto.
    assert vistos["auth"] == "Bearer clave-de-prueba"
    assert vistos["cuerpo"]["messages"][0] == {"role": "system", "content": "Sos útil"}


# Anthropic: el system va aparte, la clave en x-api-key y los bloques de
# texto "Hola" + "!" se concatenan en "Hola!".
def test_anthropic_separa_system(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    vistos = {}

    def manejador(req):
        vistos["cuerpo"] = json.loads(req.content)
        vistos["clave"] = req.headers["x-api-key"]
        return httpx.Response(200, json={"content": [{"type": "text", "text": "Hola"}, {"type": "text", "text": "!"}]})

    p = ProveedorAnthropic(cliente=httpx.Client(transport=httpx.MockTransport(manejador)))
    assert p.completar(MSGS) == "Hola!"
    assert vistos["cuerpo"]["system"] == "Sos útil" and vistos["clave"] == "k"
    assert all(m["role"] != "system" for m in vistos["cuerpo"]["messages"])


# Sin variable de entorno => ErrorLLM que nombra la variable que falta.
def test_sin_clave_falla_claro(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ErrorLLM, match="OPENAI_API_KEY"):
        ProveedorOpenAI(cliente=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200)))).completar(MSGS)


# Un 500 del servidor llega como ErrorLLM, no como excepción de httpx.
def test_error_http_se_envuelve(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    p = ProveedorOpenAI(cliente=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))))
    with pytest.raises(ErrorLLM):
        p.completar(MSGS)


# Respuestas cíclicas: 3 llamadas con ["a", "b"] => a, b, a. La fábrica
# respeta LLM_PROVEEDOR y rechaza nombres desconocidos.
def test_falso_y_fabrica(monkeypatch):
    f = ProveedorFalso(respuestas=["a", "b"])
    assert [f.completar(MSGS) for _ in range(3)] == ["a", "b", "a"] and len(f.llamadas) == 3
    monkeypatch.setenv("LLM_PROVEEDOR", "falso")
    assert crear_proveedor().nombre == "falso"
    with pytest.raises(ValueError):
        crear_proveedor("inexistente")
