"""Tests con respuestas de la API guardadas como fixtures y servidor 127.0.0.1."""
import csv
import json
from pathlib import Path
from urllib.parse import urlencode

import pytest

from wikiextractor import ApiWikipedia, extraer_articulo
from wikiextractor.api import ErrorWiki
from wikiextractor.cli import ejecutar
from wikiextractor.cliente import ClienteEducado

# Respuestas de ejemplo con el formato de la API: parse, búsqueda y error.
FX = Path(__file__).parent / "fixtures"
# Parámetros que el cliente agrega a todo pedido.
COMUN = {"format": "json", "formatversion": "2", "maxlag": "5"}


def ruta(**p):
    """Ruta con query exactamente igual a la que arma ApiWikipedia."""
    return "/w/api.php?" + urlencode(p | COMUN)


def rutas():
    """Mapa de rutas del servidor local: artículo, artículo inexistente y búsqueda."""
    j = lambda n: (200, "application/json; charset=utf-8", (FX / n).read_bytes())
    parse = lambda t: ruta(action="parse", page=t, prop="text", redirects="1", disableeditsection="1",
                           disabletoc="1")
    return {parse("Ejemplo"): j("parse.json"),
            parse("Nada"): j("error.json"),
            ruta(action="query", list="search", srsearch="ejemplo", srlimit="5"): j("buscar.json")}


def api(servidor):
    """ApiWikipedia apuntada al servidor local (sin robots.txt, como en producción)."""
    base, pedidos = servidor(rutas())
    c = ClienteEducado(user_agent="py100-wikiextractor/1.0 (test)", intervalo=0, respetar_robots=False)
    return ApiWikipedia(cliente=c, url_api=base + "/w/api.php"), pedidos


# Resumen sin referencias, infobox, secciones y tabla con colspan/rowspan expandidos.
def test_extraer_desde_fixture():
    html = json.loads((FX / "parse.json").read_text())["parse"]["text"]
    art = extraer_articulo("Ejemplo", html)
    assert art.resumen.startswith("Ejemplo es un lenguaje de programación ficticio, creado")
    assert "[2]" not in art.resumen and "historia" not in art.resumen
    assert art.infobox == {"Paradigma": "multiparadigma", "Apareció en": "1991"}
    assert art.secciones == [(2, "Historia"), (3, "Versiones")]
    assert art.tablas == [[["Versión", "Año", "Notas"], ["1.x", "1994", "Primera"], ["1.x", "2000", "Unicode"],
                           ["Sin fecha", "Sin fecha", "Futura"]]]


# Búsqueda, redirección del título, User-Agent propio en cada pedido y error de la API.
def test_api_y_user_agent(servidor):
    a, pedidos = api(servidor)
    assert a.buscar("ejemplo") == ["Ejemplo (lenguaje)", "Ejemplo"]
    titulo, html = a.html_articulo("Ejemplo")
    assert titulo == "Ejemplo (lenguaje)" and "infobox" in html
    assert all("py100-wikiextractor" in ua for _, ua in pedidos)
    with pytest.raises(ErrorWiki, match="missingtitle"):
        a.html_articulo("Nada")


# Un "idioma" que intentara cambiar el host se rechaza.
def test_idioma_invalido():
    with pytest.raises(ValueError):
        ApiWikipedia("es.evil.com/")


# Salida de texto + CSV, salida --json, modo --buscar y error (exit 1).
def test_cli(servidor, tmp_path, capsys):
    a, _ = api(servidor)
    assert ejecutar(["Ejemplo", "--tablas", str(tmp_path)], a) == 0
    out = capsys.readouterr().out
    assert out.startswith("# Ejemplo (lenguaje)") and "- Paradigma: multiparadigma" in out and "  • Versiones" in out
    filas = list(csv.reader((tmp_path / "Ejemplo_lenguaje_tabla1.csv").open()))
    assert filas[2] == ["1.x", "2000", "Unicode"]
    assert ejecutar(["Ejemplo", "--json"], a) == 0
    assert json.loads(capsys.readouterr().out)["infobox"]["Apareció en"] == "1991"
    assert ejecutar(["ejemplo", "--buscar"], a) == 0
    assert ejecutar(["Nada"], a) == 1
