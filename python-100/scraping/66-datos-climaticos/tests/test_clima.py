"""Tests: Open-Meteo simulada en 127.0.0.1 con fixtures JSON."""
import csv
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

import pytest

from clima import ApiOpenMeteo, DiaClima, Lugar, estadisticas, grafico_ascii
from clima.api import VARIABLES
from clima.cli import ejecutar
from clima.cliente import ClienteEducado

FX = Path(__file__).parent / "fixtures"
LUGAR = Lugar("Córdoba", "Argentina", -31.4135, -64.18105)


def q(**p):
    """Query string con el mismo orden de parámetros que arma la API (el servidor compara exacto)."""
    return "?" + urlencode(p)


def api(servidor):
    """Levanta las 3 APIs falsas y devuelve (ApiOpenMeteo apuntando a ellas, registro de pedidos)."""
    j = lambda n: (200, "application/json", (FX / n).read_bytes())
    base_p = dict(latitude=LUGAR.latitud, longitude=LUGAR.longitud, daily=",".join(VARIABLES), timezone="auto")
    rutas = {"/geo" + q(name="Córdoba", count=1, language="es"): j("geo.json"),
             # Ciudad inexistente: la API real responde {} sin "results".
             "/geo" + q(name="Xyzzy", count=1, language="es"): (200, "application/json", b"{}"),
             "/forecast" + q(**base_p, forecast_days=3): j("pronostico.json"),
             "/archive" + q(**base_p, start_date="2026-10-26", end_date="2026-10-28"): j("pronostico.json")}
    base, pedidos = servidor(rutas)
    return ApiOpenMeteo(ClienteEducado(intervalo=0), base + "/geo", base + "/forecast", base + "/archive"), pedidos


def test_api(servidor):
    a, pedidos = api(servidor)
    assert a.buscar_lugar("Córdoba") == LUGAR
    dias = a.pronostico(LUGAR, 3)
    # El bloque columnar se transpuso bien: el día 3 tiene sus 4 valores.
    assert dias[2] == DiaClima(date(2026, 10, 28), 22.1, 12.0, 12.5, 40.1)
    assert a.historico(LUGAR, date(2026, 10, 26), date(2026, 10, 28)) == dias
    with pytest.raises(LookupError):
        a.buscar_lugar("Xyzzy")
    # Caso borde: 30 días supera el máximo de 16 → se rechaza sin hacer el pedido.
    with pytest.raises(ValueError):
        a.pronostico(LUGAR, 30)
    # Todos los pedidos se identificaron con el User-Agent honesto del proyecto.
    assert all(ua.startswith("py100-clima/") for _, ua in pedidos)


def test_estadisticas_y_grafico():
    # El tercer día no tiene datos: debe ignorarse en medias y en el gráfico.
    dias = [DiaClima(date(2026, 1, 1), 30, 20, 0, 10), DiaClima(date(2026, 1, 2), 25, 15, 5.5, 10),
            DiaClima(date(2026, 1, 3), None, None, None, None)]
    e = estadisticas(dias)
    assert (e.t_max_media, e.t_min_media, e.lluvia_total, e.dias_lluvia) == (27.5, 17.5, 5.5, 1)
    assert e.t_max_abs == (30, "2026-01-01") and e.t_min_abs == (15, "2026-01-02")
    g = grafico_ascii(dias, ancho=10).splitlines()
    # Escala 10/(30-15): día 1 va de la columna 3 a la 10 → 7 bloques.
    assert len(g) == 2 and "☔5.5mm" in g[1] and g[0].count("▇") == 7
    assert grafico_ascii([]) == "(sin datos)"


def test_cli(servidor, tmp_path, capsys):
    a, _ = api(servidor)
    salida = tmp_path / "c.csv"
    assert ejecutar(["Córdoba", "--dias", "3", "--csv", str(salida)], a) == 0
    out = capsys.readouterr().out
    # 0 + 0.4 + 12.5 = 12.9 mm, pero sólo 1 día supera el umbral de 1 mm.
    assert "== Córdoba, Argentina" in out and "Lluvia 12.9 mm en 1 día(s)" in out
    filas = list(csv.DictReader(salida.open()))
    assert len(filas) == 3 and filas[0]["t_max"] == "28.4"
    assert ejecutar(["Córdoba", "--desde", "2026-10-26", "--hasta", "2026-10-28"], a) == 0
    assert ejecutar(["Xyzzy"], a) == 1
    assert ejecutar(["Córdoba", "--dias", "5"], a) == 2   # ruta no servida → 404
