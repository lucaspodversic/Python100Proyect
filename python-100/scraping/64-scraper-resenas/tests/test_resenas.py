"""Tests sobre fixtures locales y servidor 127.0.0.1."""
from pathlib import Path

import pytest

from resenas import PerfilResenas, Resena, clasificar, parsear_html, parsear_jsonld, puntuar, resumir
from resenas.cli import ejecutar
from resenas.cliente import ClienteEducado
from resenas.modelo import parsear_estrellas

# Páginas de reseñas inventadas (CSS y JSON-LD) y el perfil de selectores para ellas.
FX = Path(__file__).parent / "fixtures"
PERFIL = PerfilResenas.desde_json(FX / "perfil.json")


# Formatos de calificación y casos inválidos (vacío, valor mayor que el tope).
@pytest.mark.parametrize("txt,esp", [("4,0 de 5 estrellas", 4.0), ("8/10", 4.0), ("★★★☆☆", 3.0),
                                     ("4.5 out of 5", 4.5), ("", None), ("7 de 5", None), ("3", 3.0)])
def test_estrellas(txt, esp):
    assert parsear_estrellas(txt) == esp


# Incluye negación: "No es bueno" es negativa y "No es malo", positiva.
@pytest.mark.parametrize("txt,esp", [
    ("Excelente producto, lo recomiendo", "positiva"),
    ("Horrible, llegó roto", "negativa"),
    ("No es bueno", "negativa"),
    ("No es malo", "positiva"),
    ("Llegó el martes", "neutral"),
])
def test_sentimiento(txt, esp):
    assert clasificar(puntuar(txt)) == esp


# "muy" suma, y el puntaje nunca supera -1 aunque se repita la palabra.
def test_intensificador():
    assert puntuar("muy bueno") > puntuar("bueno") > 0
    assert -1 <= puntuar("horrible " * 20) < -0.9


# Autores, enlace siguiente absoluto, estrellas desde atributo, título y verificada.
def test_parser_css():
    res, sig = parsear_html((FX / "resenas1.html").read_text(), PERFIL, "http://t.test/producto/x/resenas")
    assert [r.autor for r in res] == ["Lucía", "Pedro", "Ana"] and sig == "http://t.test/producto/x/resenas?p=2"
    assert res[0].estrellas == 5.0 and res[0].verificada and res[0].titulo == "Excelentes"
    assert not res[1].verificada


# Calificaciones en otra escala se normalizan a 5.
def test_parser_jsonld():
    res = parsear_jsonld((FX / "jsonld.html").read_text())
    assert [(r.autor, r.estrellas) for r in res] == [("Marta", 4.5), ("Raúl", 2.0)]


# La tercera reseña (5 estrellas, texto negativo) es una discrepancia.
def test_resumen():
    rs = [Resena("a", "Excelente, lo recomiendo", 5), Resena("b", "Horrible y roto", 1),
          Resena("c", "Pésimo, no funciona", 5)]
    s = resumir(rs)
    assert s.promedio_estrellas == 3.67 and s.distribucion[5] == 2 and s.discrepancias == 1
    assert s.sentimientos == {"positiva": 1, "negativa": 2} and "horrible" in s.temas_negativos


# Dos páginas en el servidor local; la reseña repetida en la segunda se descarta.
def test_cli_servidor_local(servidor, tmp_path, capsys):
    html = lambda n: (200, "text/html; charset=utf-8", (FX / n).read_bytes())
    base, pedidos = servidor({"/robots.txt": (200, "text/plain", b"User-agent: *\nAllow: /\n"),
                              "/producto/x/resenas": html("resenas1.html"),
                              "/producto/x/resenas?p=2": html("resenas2.html")})
    csv = tmp_path / "r.csv"
    assert ejecutar(["--url", base + "/producto/x/resenas", "--perfil", str(FX / "perfil.json"),
                     "--csv", str(csv)], ClienteEducado(intervalo=0)) == 0
    out = capsys.readouterr().out
    assert "Reseñas: 4" in out and "⚠ 1 reseña(s)" in out    # Lucía duplicada se descarta
    assert len(csv.read_text().splitlines()) == 5
    assert all(ua.startswith("py100-resenas/") for _, ua in pedidos)


# Archivo local sin red; y si robots.txt prohíbe todo, exit 3 sin pedir la página.
def test_cli_archivo_y_robots(servidor, capsys):
    assert ejecutar(["--archivo", str(FX / "jsonld.html")]) == 0
    assert "Reseñas: 2" in capsys.readouterr().out
    base, pedidos = servidor({"/robots.txt": (200, "text/plain", b"User-agent: *\nDisallow: /\n")})
    assert ejecutar(["--url", base + "/p"], ClienteEducado(intervalo=0)) == 3
    assert [p for p, _ in pedidos] == ["/robots.txt"]
