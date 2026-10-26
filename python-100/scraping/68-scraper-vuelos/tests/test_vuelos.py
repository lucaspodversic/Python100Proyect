"""Tests sobre fixtures locales; ningún pedido a sitios reales."""
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from vuelos import (Criterio, HistorialPrecios, PerfilVuelos, filtrar, ordenar, parsear_duracion, parsear_html,
                    parsear_json, parsear_precio, resumen_por_aerolinea)
from vuelos.cli import ejecutar
from vuelos.cliente import ClienteEducado

FX = Path(__file__).parent / "fixtures"
# Perfil de la página de ejemplo: tarjetas "li.oferta", ruta fija COR→LIM.
PERFIL = PerfilVuelos.desde_json((FX / "perfil.json").read_text())


def cargar():
    """Parsea resultados.html: 4 tarjetas, la última ("Rota") sin fecha ni duración."""
    return parsear_html((FX / "resultados.html").read_text(), PERFIL)


# Formatos latino y anglosajón, con y sin moneda; "1,234" (3 dígitos tras la coma) = miles.
@pytest.mark.parametrize("texto,esperado", [
    ("US$ 1.234,50", (Decimal("1234.50"), "USD")), ("€1,234.50", (Decimal("1234.50"), "EUR")),
    ("$ 1.234", (Decimal("1234"), "USD")), ("ARS 98.500", (Decimal("98500"), "ARS")),
    ("210,5", (Decimal("210.5"), "")), ("1,234", (Decimal("1234"), ""))])
def test_precio(texto, esperado):
    assert parsear_precio(texto) == esperado


def test_precio_invalido():
    # Caso borde: texto sin ningún dígito.
    with pytest.raises(ValueError):
        parsear_precio("consultar")


# Variantes con espacios, "min", ISO 8601 y sólo horas.
@pytest.mark.parametrize("texto,minutos", [("2h 05m", 125), ("5 h 10 min", 310), ("95 min", 95), ("PT2H35M", 155), ("3h", 180)])
def test_duracion(texto, minutos):
    assert parsear_duracion(texto) == minutos


def test_parser_html():
    vuelos, errores = cargar()
    # La tarjeta rota (índice 3) se reporta sin descartar las otras tres.
    assert len(vuelos) == 3 and len(errores) == 1 and "tarjeta 3" in errores[0]
    v = vuelos[0]
    # Origen/destino vienen del perfil; "Directo" → 0 escalas; "US$ 210,50" → 210.50.
    assert (v.origen, v.destino, v.escalas, v.precio, v.duracion_min) == ("COR", "LIM", 0, Decimal("210.50"), 125)
    # Sin selector de llegada: 07:15 + 2h05 = 09:20.
    assert v.llegada == datetime(2026, 11, 20, 9, 20)


def test_parser_json():
    # Mapeo estilo API: rutas con índices de lista ("segments.0...").
    mapeo = {"aerolinea": "airline", "numero": "segments.0.number", "origen": "segments.0.dep.iata",
             "destino": "segments.0.arr.iata", "salida": "segments.0.dep.at", "llegada": "segments.0.arr.at",
             "precio": "price.total", "moneda": "price.currency", "escalas": "stops"}
    vuelos, errores = parsear_json(json.loads((FX / "api.json").read_text()), "data", mapeo)
    # La segunda oferta no tiene total ni segmentos → error, no excepción.
    assert len(vuelos) == 1 and len(errores) == 1
    # "mad" se normaliza a "MAD"; 10:00 → 22:30 = 750 min.
    assert (vuelos[0].origen, vuelos[0].precio, vuelos[0].moneda, vuelos[0].duracion_min) == ("MAD", Decimal("199.90"), "EUR", 750)


def test_ordenar_filtrar_resumen():
    vuelos, _ = cargar()
    assert [v.numero for v in ordenar(vuelos)] == ["LA330", "AS101", "AS205"]
    assert [v.numero for v in ordenar(vuelos, Criterio.DURACION)][0] == "AS101"
    # 150 + 20*310/60 = 253.3 > 210.5 + 20*125/60 = 252.2 → el directo gana en equilibrio
    assert ordenar(vuelos, Criterio.EQUILIBRIO)[0].numero == "AS101"
    # AS205 es directo pero cuesta 1180 > 500.
    assert [v.numero for v in filtrar(vuelos, max_escalas=0, precio_max=Decimal(500))] == ["AS101"]
    # Sólo LA330 sale entre las 12 y las 18 (13:40).
    assert [v.numero for v in filtrar(vuelos, salida_desde=12, salida_hasta=18)] == ["LA330"]
    assert resumen_por_aerolinea(vuelos) == {"AeroSur": (2, Decimal("210.50")), "LatAir": (1, Decimal("150"))}


def test_historial(tmp_path):
    vuelos, _ = cargar()
    h = HistorialPrecios(tmp_path / "h.csv")
    # Sin historial no hay bajas posibles.
    assert h.bajas(vuelos) == []
    h.registrar(vuelos, datetime(2026, 10, 1))
    import dataclasses
    # Mismo vuelo (misma clave) más barato → baja; vuelos[1] con el mismo precio → no.
    barato = dataclasses.replace(vuelos[0], precio=Decimal("180"))
    assert h.bajas([barato, vuelos[1]]) == [(barato, Decimal("210.50"))]


def test_cli(servidor, tmp_path, capsys):
    # Servidor local con robots.txt que prohíbe /privado.
    base, pedidos = servidor({"/robots.txt": (200, "text/plain", b"User-agent: *\nDisallow: /privado\n"),
                              "/buscar": (200, "text/html", (FX / "resultados.html").read_bytes())})
    c = ClienteEducado(intervalo=0)
    perfil = str(FX / "perfil.json")
    hist = str(tmp_path / "h.csv")
    assert ejecutar(["--url", base + "/buscar", "--perfil", perfil, "--max-escalas", "0", "--historial", hist],
                    c, lambda: datetime(2026, 10, 26)) == 0
    out = capsys.readouterr().out
    # Primera fila = directo más barato, con columnas alineadas (aerolínea a 12 caracteres).
    assert out.splitlines()[0].startswith("AeroSur      AS101") and "AeroSur: 2 opción(es), desde 210.50" in out
    assert ejecutar(["--archivo", str(FX / "resultados.html"), "--perfil", perfil, "--orden", "duracion"]) == 0
    # robots.txt prohíbe /privado → exit 3 y el pedido NUNCA llega al servidor.
    assert ejecutar(["--url", base + "/privado", "--perfil", perfil], c) == 3
    assert "/privado" not in [p for p, _ in pedidos]
    # HTML sin tarjetas → exit 2.
    vacio = tmp_path / "v.html"; vacio.write_text("<html></html>")
    assert ejecutar(["--archivo", str(vacio), "--perfil", perfil]) == 2
