"""Tests del monitor de sentimiento: fuentes con fixtures/MockTransport, sin red."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from sentimiento.analizador import clasificar, lexico
from sentimiento.fuentes import FuenteArchivo, FuenteReddit, FuenteTwitter, Publicacion
from sentimiento.llm import ProveedorFalso
from sentimiento.monitor import Monitor

FEED = Path(__file__).parent / "feed.jsonl"
# El feed de prueba tiene 10 publicaciones de 10:00 a 10:09 (una por
# minuto); la id 3 no menciona AcmeBank. T0 = 10:10.
T0 = datetime(2026, 10, 26, 10, 10, tzinfo=timezone.utc)


def pub(i, texto):
    return Publicacion(str(i), texto, "x", T0, "test")


@pytest.mark.parametrize("texto,esperado", [
    ("Excelente servicio, lo recomiendo", "positivo"),
    # "Excelente" + "recomiendo" = +2/2 = 1,0; "Horrible" + "estafa" = -1,0.
    ("Horrible, una estafa", "negativo"),
    ("No es bueno", "negativo"),        # negación invierte
    # Sin palabras con carga => score 0,0 => neutral.
    ("Hoy es martes", "neutral"),
])
def test_lexico(texto, esperado):
    assert lexico(texto)[0] == esperado


def test_clasificar_llm_por_lotes_con_respaldo():
    pubs = [pub(1, "texto a"), pub(2, "horrible"), pub(3, "x")]
    # El LLM resuelve 1 y 3 (3 con etiqueta inválida) -> 2 y 3 caen al léxico
    llm = ProveedorFalso(respuestas=['[{"id":"1","sentimiento":"positivo","score":0.9},'
                                     '{"id":"3","sentimiento":"enojado","score":5}]'])
    # "horrible" => -1/1 = -1,0; "x" no tiene carga => ("neutral", 0,0).
    r = clasificar(pubs, llm, lote=10)
    assert r == {"1": ("positivo", 0.9), "2": ("negativo", -1.0), "3": ("neutral", 0.0)}
    assert len(llm.llamadas) == 1   # un solo pedido para todo el lote


def test_fuente_archivo_filtra_y_avanza():
    f = FuenteArchivo(FEED, tamano_lote=5)
    # Primer lote = filas 1..5, la 3 se filtra. El segundo lote empieza en la 6
    # y el tercero está vacío (solo hay 10 filas).
    assert [p.id for p in f.obtener("acmebank")] == ["1", "2", "4", "5"]
    assert [p.id for p in f.obtener("acmebank")][0] == "6"
    assert f.obtener("acmebank") == []


def test_monitor_alerta_con_enfriamiento():
    m = Monitor([FuenteArchivo(FEED, tamano_lote=5)], "AcmeBank", minimo_muestras=5)
    assert m.ciclo(T0) is None                         # 4 muestras: insuficiente
    # Tras 2 ciclos hay 9 muestras: positivas la 1 y la 2; negativas 4 a 10
    # (la 5 por "no es buena") = 7 => 7 / 9 = 0,777... => 0,78 > 0,5.
    alerta = m.ciclo(T0 + timedelta(minutes=1))
    assert alerta and alerta.muestras == 9 and alerta.proporcion_negativa == 0.78
    assert m.metricas()["positivo"] == 2
    # Sigue negativo, pero pasó 1 minuto de los 10 de enfriamiento.
    assert m.ciclo(T0 + timedelta(minutes=2)) is None  # enfriamiento


def test_ventana_descarta_viejos():
    m = Monitor([FuenteArchivo(FEED, tamano_lote=10)], "AcmeBank", ventana=timedelta(minutes=5))
    # Ventana de 5 min: se descartan las anteriores a 10:05 => ids 6..10 = 5.
    m.ciclo(T0)  # T0=10:10 -> solo quedan las de 10:05 en adelante
    assert m.metricas()["muestras"] == 5


def test_monitor_deduplica_y_tolera_fuente_caida():
    class Repite:
        nombre = "repite"
        def obtener(self, c): return [pub("a", "excelente")]
    class Caida:
        nombre = "caida"
        def obtener(self, c): raise httpx.ConnectError("sin red")
    m = Monitor([Repite(), Caida()], "x")
    # Repite devuelve la misma "a" dos veces (se cuenta una) y Caida lanza
    # error en cada ciclo sin frenar el monitor => 1 muestra.
    m.ciclo(T0); m.ciclo(T0)
    assert m.metricas()["muestras"] == 1


def test_reddit_con_mock():
    datos = {"data": {"children": [{"data": {"id": "abc", "title": "AcmeBank genial", "selftext": "",
                                             "author": "u1", "created_utc": 1793000000}}]}}
    def manejador(req):
        assert req.url.params["q"] == "AcmeBank" and req.url.path == "/r/finanzas/search.json"
        return httpx.Response(200, json=datos)
    f = FuenteReddit(httpx.Client(transport=httpx.MockTransport(manejador)), subreddit="finanzas")
    p = f.obtener("AcmeBank")[0]
    assert p.id == "reddit:abc" and p.fuente == "reddit"


def test_twitter_con_mock_y_since_id(monkeypatch):
    monkeypatch.setenv("X_BEARER_TOKEN", "tkn")
    pedidos = []
    def manejador(req):
        pedidos.append(req)
        return httpx.Response(200, json={"data": [{"id": "99", "text": "AcmeBank caído", "created_at": "2026-10-26T10:00:00Z"}],
                                         "meta": {"newest_id": "99"}})
    f = FuenteTwitter(httpx.Client(transport=httpx.MockTransport(manejador)))
    assert f.obtener("AcmeBank")[0].id == "tw:99"
    f.obtener("AcmeBank")
    assert pedidos[0].headers["authorization"] == "Bearer tkn"
    # El primer pedido trae todo; el segundo pide solo lo posterior al id 99.
    assert "since_id" not in pedidos[0].url.params and pedidos[1].url.params["since_id"] == "99"
