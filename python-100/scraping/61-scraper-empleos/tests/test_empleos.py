"""Tests contra fixtures locales y un servidor en 127.0.0.1 (sin Internet)."""
import csv
import json
from pathlib import Path

import pytest

from empleos import Filtro, Oferta, PerfilSelectores, ejecutar_pipeline, exportar, parsear_html, parsear_jsonld, parsear_salario
from empleos.cli import ejecutar
from empleos.cliente import ClienteEducado

# HTML de ejemplo guardados en el repo: los tests no dependen de ningún sitio real.
FX = Path(__file__).parent / "fixtures"
PERFIL = PerfilSelectores.desde_json(FX / "perfil.json")


# Rango con miles y €, sufijo k, pesos con miles, sin cifra y "mil" con coma decimal.
@pytest.mark.parametrize("txt,esp", [
    ("40.000 - 55.000 €", (40000, 55000, "EUR")), ("US$ 3k", (3000, 3000, "USD")),
    ("$ 900.000", (900000, 900000, "ARS")), ("A convenir", (None, None, "")), ("2,5 mil usd", (2500, 2500, "USD")),
])
def test_salarios(txt, esp):
    assert parsear_salario(txt) == esp


# Dos tarjetas válidas (la incompleta se ignora), enlace absoluto, remoto detectado y paginación.
def test_parser_css():
    ofertas, sig = parsear_html((FX / "pagina1.html").read_text(), PERFIL, "http://x.test/empleos")
    assert len(ofertas) == 2 and sig == "http://x.test/empleos?p=2"
    o = ofertas[0]
    assert (o.titulo, o.empresa, o.url, o.remoto) == ("Desarrollador/a Python Senior", "Acme Software",
                                                     "http://x.test/oferta/101", True)
    assert o.etiquetas == ("python", "django") and o.salario_max == 55000


# JobPosting con dirección y rango de salario, URL relativa resuelta y trabajo remoto.
def test_parser_jsonld():
    ofertas = parsear_jsonld((FX / "jsonld.html").read_text(), "http://x.test/")
    assert [o.titulo for o in ofertas] == ["Ingeniera de Datos", "SRE"]
    assert ofertas[0].ubicacion == "Valencia, ES" and ofertas[0].salario_min == 35000
    assert ofertas[0].url == "http://x.test/j/1" and ofertas[1].remoto


# Palabra y ubicación, exclusión, sólo remoto y salario mínimo.
def test_filtro():
    o = Oferta("Dev Python", "A", "Madrid", etiquetas=("django",), salario_max=50000)
    assert Filtro(("python",), ubicacion="madrid").acepta(o)
    assert not Filtro(excluir=("django",)).acepta(o)
    assert not Filtro(solo_remoto=True).acepta(o)
    assert not Filtro(salario_minimo=60000).acepta(o)


def _rutas():
    """Rutas del servidor local: robots.txt y las dos páginas del listado."""
    html = lambda n: (200, "text/html; charset=utf-8", (FX / n).read_bytes())
    return {"/robots.txt": (200, "text/plain", b"User-agent: *\nDisallow: /admin\n"),
            "/empleos": html("pagina1.html"), "/empleos?p=2": html("pagina2.html")}


# Pipeline completo contra 127.0.0.1: robots primero, dos páginas, deduplicación y User-Agent propio.
def test_pipeline_servidor_local(servidor, tmp_path):
    base, pedidos = servidor(_rutas())
    c = ClienteEducado(intervalo=0)
    ofertas = ejecutar_pipeline(c, base + "/empleos", PERFIL, Filtro(("desarrollador",)))
    assert [o.url.rsplit("/", 1)[1] for o in ofertas] == ["101", "103"]  # deduplicada la 101
    assert [p for p, _ in pedidos] == ["/robots.txt", "/empleos", "/empleos?p=2"]
    assert all(ua.startswith("py100-empleos/") for _, ua in pedidos)
    exportar(ofertas, tmp_path / "o.csv")
    assert len(list(csv.DictReader((tmp_path / "o.csv").open()))) == 2


# Exporta JSON; una URL prohibida por robots.txt da exit 3 sin pedirse jamás.
def test_cli(servidor, tmp_path, capsys):
    base, pedidos = servidor(_rutas())
    salida = tmp_path / "o.json"
    assert ejecutar(["--url", base + "/empleos", "--perfil", str(FX / "perfil.json"), "-k", "python",
                     "-o", str(salida)], ClienteEducado(intervalo=0)) == 0
    assert len(json.loads(salida.read_text())) == 2
    assert ejecutar(["--url", base + "/admin"], ClienteEducado(intervalo=0)) == 3
    assert "/admin" not in [p for p, _ in pedidos]  # nunca se pidió la ruta prohibida
