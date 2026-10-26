"""Tests del cliente real con httpx.MockTransport: se verifica la petición sin tocar la red."""
import json

import httpx
import pytest

from clientex.api import (ClienteXAPI, ErrorAutenticacion, ErrorLimite, ErrorX, ServicioFalso, VAR_TOKEN,
                          VAR_TOKEN_USUARIO)


def cliente(manejador, token="tok-123"):
    """Cliente con transporte simulado (sin red) y reloj fijo en t=1000."""
    return ClienteXAPI(token=token, transporte=httpx.MockTransport(manejador), reloj=lambda: 1000)


def test_sin_token_falla(monkeypatch):
    """Sin token el mensaje dice qué variable definir."""
    monkeypatch.delenv(VAR_TOKEN, raising=False)
    monkeypatch.delenv(VAR_TOKEN_USUARIO, raising=False)
    with pytest.raises(ErrorAutenticacion, match=VAR_TOKEN):
        ClienteXAPI()


def test_token_desde_entorno_y_no_se_filtra_en_repr(monkeypatch):
    """El token del entorno va en el header Bearer y no aparece en repr."""
    monkeypatch.setenv(VAR_TOKEN, "secreto-env")
    vistos = []

    def h(req):
        """Servidor falso: anota el header recibido."""
        vistos.append(req.headers["authorization"])
        return httpx.Response(200, json={"data": {"id": "9", "username": "yo"}})
    c = ClienteXAPI(transporte=httpx.MockTransport(h))
    assert c.yo()["username"] == "yo"
    assert vistos == ["Bearer secreto-env"]
    assert "secreto" not in repr(c)


def test_buscar_parsea_autores_y_paginacion():
    """Ruta y parámetros correctos; el autor se resuelve vía includes (author_id 7 → ana) y se
    propaga el next_token.
    """
    def h(req):
        """Servidor falso que verifica la petición y responde una página."""
        assert req.url.path == "/2/tweets/search/recent"
        assert req.url.params["query"] == "python"
        assert req.url.params["next_token"] == "abc"
        return httpx.Response(200, json={
            "data": [{"id": "1", "text": "hola python", "author_id": "7", "public_metrics": {"like_count": 5}}],
            "includes": {"users": [{"id": "7", "username": "ana"}]},
            "meta": {"next_token": "def"}})
    p = cliente(h).buscar("python", "abc")
    assert p.posts[0].autor == "ana" and p.posts[0].me_gusta == 5
    assert p.siguiente == "def"


def test_publicar_envia_reply():
    """El cuerpo lleva el reply con el id al que responde."""
    cuerpos = []

    def h(req):
        """Servidor falso que guarda el cuerpo enviado."""
        assert req.method == "POST" and req.url.path == "/2/tweets"
        cuerpos.append(json.loads(req.content))
        return httpx.Response(201, json={"data": {"id": "55", "text": "hola"}})
    post = cliente(h).publicar("hola", responde_a="44")
    assert post.id == "55"
    assert cuerpos == [{"text": "hola", "reply": {"in_reply_to_tweet_id": "44"}}]


# 401 = token inválido; 403 = sin permiso (p. ej. falta tweet.write); 500 = error genérico.
@pytest.mark.parametrize("codigo, error", [(401, ErrorAutenticacion), (403, ErrorAutenticacion), (500, ErrorX)])
def test_errores_http(codigo, error):
    """Cada código HTTP se traduce a su excepción."""
    with pytest.raises(error):
        cliente(lambda req: httpx.Response(codigo, json={"detail": "x"})).yo()


def test_limite_calcula_espera():
    """Reinicio en el epoch 1060 y reloj en 1000 → esperar 60 s."""
    h = lambda req: httpx.Response(429, headers={"x-rate-limit-reset": "1060"})
    with pytest.raises(ErrorLimite) as e:
        cliente(h).yo()
    assert e.value.espera == 60


def test_error_de_red_envuelto():
    """Un error de conexión llega como ErrorX legible, no como excepción de httpx."""
    def h(req):
        """Simula que no hay red."""
        raise httpx.ConnectError("sin red")
    with pytest.raises(ErrorX, match="red"):
        cliente(h).yo()


def test_busqueda_vacia():
    """Una búsqueda con solo espacios se rechaza sin llamar a la API."""
    with pytest.raises(ErrorX):
        cliente(lambda r: httpx.Response(200, json={})).buscar("  ")


def test_servicio_falso_pagina():
    """Con páginas de 1: 'b' (más nuevo) y luego 'a'; la última página no tiene cursor."""
    s = ServicioFalso(tam_pagina=1)
    s.publicar("a"); s.publicar("b")
    p1 = s.publicaciones("1")
    p2 = s.publicaciones("1", p1.siguiente)
    assert [p.texto for p in p1.posts + p2.posts] == ["b", "a"] and p2.siguiente is None
