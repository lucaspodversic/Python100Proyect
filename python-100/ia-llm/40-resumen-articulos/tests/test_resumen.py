"""Tests del resumidor: extracción desde fixture HTML local, map-reduce y fallback. Sin red."""
from pathlib import Path

import httpx
import pytest

from resumen.extraccion import extraer
from resumen.llm import ErrorLLM, ProveedorFalso
from resumen.obtencion import ErrorObtencion, FetcherFalso, FetcherHTTP
from resumen.resumidor import a_markdown, extractivo, resumir, trocear

FIX = Path(__file__).parent / "articulo.html"
URL = "https://diario.ejemplo/solar"


@pytest.fixture()
def articulo():
    return extraer(FetcherFalso({URL: FIX}).obtener(URL))


# El fixture trae og:title, meta author y article:published_time con hora.
def test_extraccion_metadatos(articulo):
    assert articulo.titulo == "La energía solar crece en Argentina"
    assert articulo.autor == "Laura Pérez" and articulo.fecha == "2026-10-20"


def test_extraccion_ignora_ruido(articulo):
    texto = articulo.texto
    assert texto.startswith("La capacidad instalada")
    assert "Inversiones y empleo" in articulo.parrafos
    for ruido in ("Publicidad", "newsletter", "Derechos", "tracking", "menú", "Corto."):
        assert ruido.lower() not in texto.lower()
    # El fixture incluye nav, aside de publicidad, footer, script y un <p>
    # "Corto." (< 25 caracteres): nada de eso debe colarse. Quedan 6 bloques.
    assert len(articulo.parrafos) == 6


def test_titulo_sin_og_y_html_roto():
    # Sin og:title: usa <title> y quita " | Sitio". El <p> nunca se cierra y
    # hay un </b> huérfano: igual se recupera el párrafo.
    a = extraer("<title>Nota X | Sitio</title><body><div><p>Un párrafo suficientemente largo para contar.</div></b></body>")
    assert a.titulo == "Nota X" and a.parrafos == ["Un párrafo suficientemente largo para contar."]


def test_resumen_llm_un_trozo(articulo):
    llm = ProveedorFalso(respuestas=["- La solar creció 40%"])
    r = resumir(articulo, llm)
    assert r.metodo == "llm" and len(llm.llamadas) == 1
    # llamadas[0] = mensajes del primer pedido; [1] = mensaje del usuario.
    assert llm.llamadas[0][1].contenido.startswith("# La energía solar")


def test_resumen_map_reduce(articulo):
    llm = ProveedorFalso(funcion=lambda ms: f"resumen de {len(ms[1].contenido)} chars")
    # Con 300 caracteres por trozo el artículo se parte en varios (>= 3).
    r = resumir(articulo, llm, max_chars=300)
    assert r.metodo == "llm-mapreduce" and r.trozos >= 3
    # Un pedido por trozo (map) más uno final que los combina (reduce).
    assert len(llm.llamadas) == r.trozos + 1     # N map + 1 reduce


def test_fallback_extractivo(articulo):
    def rompe(_):
        raise ErrorLLM("x")
    r = resumir(articulo, ProveedorFalso(funcion=rompe))
    # Por defecto el extractivo da 3 viñetas.
    assert r.metodo == "extractivo" and r.puntos.count("- ") == 3
    assert "solar" in r.puntos


def test_extractivo_respeta_orden():
    texto = "El gato come pescado fresco hoy. El perro duerme en la cucha. El gato y el pescado son amigos del gato."
    # "gato" y "pescado" son las más frecuentes: ganan la 1.ª y la 3.ª
    # oración, y se devuelven en orden original (la 1.ª va primero).
    salida = extractivo(texto, n=2)
    lineas = salida.splitlines()
    assert lineas[0].startswith("- El gato come") and len(lineas) == 2


def test_trocear():
    # 10 + 10 + 2 = 22 > 15 => dos trozos.
    assert trocear("a" * 10 + "\n\n" + "b" * 10, 15) == ["a" * 10, "b" * 10]


def test_markdown(articulo):
    md = a_markdown(resumir(articulo, None), articulo, URL)
    assert md.startswith("# La energía solar") and "Laura Pérez · 2026-10-20" in md and f"<{URL}>" in md


def test_fetcher_http_seguridad():
    html = httpx.MockTransport(lambda r: httpx.Response(200, html="<p>x</p>"))
    pdf = httpx.MockTransport(lambda r: httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"}))
    # 5000 bytes contra un máximo de 1000 => "demasiado grande".
    grande = httpx.MockTransport(lambda r: httpx.Response(200, html="x" * 5000))
    assert FetcherHTTP(httpx.Client(transport=html)).obtener("https://e.com") == "<p>x</p>"
    with pytest.raises(ErrorObtencion, match="http"):
        FetcherHTTP(httpx.Client(transport=html)).obtener("file:///etc/passwd")
    with pytest.raises(ErrorObtencion, match="No es HTML"):
        FetcherHTTP(httpx.Client(transport=pdf)).obtener("https://e.com/a.pdf")
    with pytest.raises(ErrorObtencion, match="grande"):
        FetcherHTTP(httpx.Client(transport=grande), max_bytes=1000).obtener("https://e.com")
    with pytest.raises(ErrorObtencion):
        FetcherFalso({}).obtener("https://nada")
