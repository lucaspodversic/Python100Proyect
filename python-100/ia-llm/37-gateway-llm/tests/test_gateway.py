"""Tests del gateway: auth, fallback, reintentos, caché, cuotas, adaptadores con MockTransport."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from gateway.app import crear_app
from gateway.llm import ErrorLLM, ProveedorAnthropic, ProveedorFalso, ProveedorOpenAI
from gateway.nucleo import CacheLRU, Gateway, LimitadorTasa, Ruta

AUTH = {"Authorization": "Bearer secreto"}
CHAT = {"modelo": "m", "mensajes": [{"rol": "user", "contenido": "Hola"}]}


# Falla las primeras n llamadas y luego responde: simula un proveedor que
# se recupera (n=99 => siempre caído en la práctica).
class Roto:
    """Proveedor que falla las primeras `n` veces."""
    def __init__(self, n=99, nombre="roto"):
        self.n, self.nombre, self.llamadas = n, nombre, 0

    def completar(self, mensajes, **kw):
        self.llamadas += 1
        if self.llamadas <= self.n:
            raise ErrorLLM("caído")
        return "recuperado"


def cliente(proveedores, **kw):
    # costo_por_1k=1.0 hace que el costo sea simplemente tokens / 1000.
    esperas = []  # registra los tiempos de backoff sin dormir de verdad
    gw = Gateway({"m": Ruta(proveedores, costo_por_1k=1.0)}, dormir=esperas.append, **kw)
    return TestClient(crear_app(gw, ["secreto"])), gw, esperas


def test_auth():
    c, _, _ = cliente([ProveedorFalso()])
    assert c.post("/v1/chat", json=CHAT).status_code == 401
    assert c.post("/v1/chat", json=CHAT, headers={"Authorization": "Bearer otra"}).status_code == 401
    assert c.get("/salud").json()["ok"]


def test_chat_basico_y_uso():
    c, _, _ = cliente([ProveedorFalso(respuestas=["respuesta larga " * 4])])
    r = c.post("/v1/chat", json=CHAT, headers=AUTH).json()
    # "respuesta larga " son 16 caracteres x 4 = 64 => 64 // 4 = 16 tokens.
    assert r["proveedor"] == "falso" and r["cache"] is False and r["uso"]["tokens_salida"] == 16
    u = c.get("/v1/uso", headers=AUTH).json()
    # Entrada "Hola" = 1 token + 16 de salida = 17 tokens => 17 / 1000 x 1,0 = 0,017.
    assert u["pedidos"] == 1 and u["costo_usd"] == pytest.approx(0.017)
    assert c.post("/v1/chat", json={**CHAT, "modelo": "x"}, headers=AUTH).status_code == 404


def test_reintentos_con_backoff():
    # Falla 2 veces, la 3.ª funciona: 2 esperas (0,5 y 1,0) e intentos = 3.
    roto = Roto(n=2)
    c, _, esperas = cliente([roto], reintentos=2)
    r = c.post("/v1/chat", json=CHAT, headers=AUTH).json()
    assert r["contenido"] == "recuperado" and r["intentos"] == 3
    assert esperas == [0.5, 1.0]  # backoff exponencial


# Roto falla 2 veces (1 + 1 reintento) y se pasa al siguiente proveedor.
def test_fallback_a_segundo_proveedor():
    c, _, _ = cliente([Roto(), ProveedorFalso(respuestas=["plan B"])], reintentos=1)
    r = c.post("/v1/chat", json=CHAT, headers=AUTH).json()
    assert r["proveedor"] == "falso" and r["contenido"] == "plan B"


def test_todos_fallan_502():
    c, _, _ = cliente([Roto(), Roto(nombre="roto2")], reintentos=0)
    r = c.post("/v1/chat", json=CHAT, headers=AUTH)
    # Sin reintentos: 1 intento por proveedor x 2 proveedores = 2.
    assert r.status_code == 502 and "2 intentos" in r.json()["detail"]


# 1.º pedido: llama al LLM y cachea. 2.º igual: acierto. 3.º con
# temperatura 0,7: no usa caché => 2 llamadas reales y 1 acierto.
def test_cache_solo_temperatura_cero():
    falso = ProveedorFalso()
    c, gw, _ = cliente([falso])
    c.post("/v1/chat", json=CHAT, headers=AUTH)
    assert c.post("/v1/chat", json=CHAT, headers=AUTH).json()["cache"] is True
    c.post("/v1/chat", json={**CHAT, "temperatura": 0.7}, headers=AUTH)
    assert len(falso.llamadas) == 2 and gw.cache.aciertos == 1


def test_cache_lru_descarta_viejo():
    lru = CacheLRU(capacidad=2)
    # Capacidad 2: leer "a" la hace reciente, así que al entrar "c" sale "b".
    lru.guardar("a", {}); lru.guardar("b", {}); lru.obtener("a"); lru.guardar("c", {})
    assert lru.obtener("b") is None and lru.obtener("a") == {}


def test_limitador_tasa():
    t = [0.0]
    lim = LimitadorTasa(por_minuto=2, reloj=lambda: t[0])
    assert lim.permitir("k") and lim.permitir("k") and not lim.permitir("k")
    # 2 por minuto = 1 ficha cada 30 s: entra un pedido y el siguiente no.
    t[0] = 30  # 30 s -> recarga 1 ficha
    assert lim.permitir("k") and not lim.permitir("k")
    gw = Gateway({"m": Ruta([ProveedorFalso()])})
    # Reloj congelado y 1 por minuto: el segundo pedido da 429.
    c = TestClient(crear_app(gw, ["secreto"], LimitadorTasa(por_minuto=1, reloj=lambda: 0.0)))
    c.post("/v1/chat", json=CHAT, headers=AUTH)
    assert c.post("/v1/chat", json=CHAT, headers=AUTH).status_code == 429


def test_validacion_pedido():
    c, _, _ = cliente([ProveedorFalso()])
    assert c.post("/v1/chat", json={"mensajes": []}, headers=AUTH).status_code == 422
    assert c.post("/v1/chat", json={**CHAT, "temperatura": 5}, headers=AUTH).status_code == 422


def test_adaptadores_reales_con_mock_transport(monkeypatch):
    """OpenAI cae (500) -> fallback a Anthropic, todo con transporte simulado (sin red)."""
    monkeypatch.setenv("OPENAI_API_KEY", "ko"); monkeypatch.setenv("ANTHROPIC_API_KEY", "ka")
    vistos = []

    def manejador(req: httpx.Request):
        vistos.append(req.url.host)
        if req.url.host == "api.openai.com":
            return httpx.Response(500, json={"error": "caído"})
        assert json.loads(req.content)["messages"][0]["content"] == "Hola"
        return httpx.Response(200, json={"content": [{"type": "text", "text": "Hola desde Anthropic"}]})

    http = httpx.Client(transport=httpx.MockTransport(manejador))
    c, _, _ = cliente([ProveedorOpenAI(cliente=http), ProveedorAnthropic(cliente=http)], reintentos=0)
    r = c.post("/v1/chat", json=CHAT, headers=AUTH).json()
    assert r["proveedor"] == "anthropic" and r["contenido"] == "Hola desde Anthropic"
    assert vistos == ["api.openai.com", "api.anthropic.com"]
