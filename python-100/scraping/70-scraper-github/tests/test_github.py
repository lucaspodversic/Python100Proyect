"""Tests: API de GitHub simulada en 127.0.0.1 y fetchers falsos. Sin red real."""
import csv
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import pytest

from github_tendencias import ApiGitHub, LimiteExcedido, construir_consulta, exportar_csv, markdown, ordenar_por_ritmo
from github_tendencias.cli import ejecutar
from github_tendencias.cliente import ClienteEducado, Respuesta

FX = Path(__file__).parent / "fixtures"
# Reloj fijo: los cálculos de estrellas/día son deterministas.
AHORA = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)
# Consulta que genera tendencias(7 días, hoy=26/10, lenguaje=python).
Q = "created:>=2026-10-19 language:python"


def ruta(q, pagina, por=2):
    """Path+query exacto que pide ApiGitHub (mismo orden de parámetros) para registrarlo en el servidor."""
    return "/search/repositories?" + urlencode({"q": q, "sort": "stars", "order": "desc", "per_page": por, "page": pagina})


@pytest.fixture
def api(servidor):
    """ApiGitHub contra el servidor local: página 1 con 2 repos y página 2 con 1."""
    j = lambda n: (200, "application/json", (FX / n).read_bytes())
    base, pedidos = servidor({ruta(Q, 1): j("pagina1.json"), ruta(Q, 2): j("pagina2.json")})
    return ApiGitHub(ClienteEducado(intervalo=0, respetar_robots=False), base=base), pedidos


def test_consulta():
    # Lenguaje con espacio → entre comillas; todos los calificadores presentes.
    assert construir_consulta(date(2026, 10, 1), "Jupyter Notebook", "ml", 50) == \
        'created:>=2026-10-01 language:"Jupyter Notebook" topic:ml stars:>=50'


def test_paginacion(api):
    a, pedidos = api
    # cantidad=2 → per_page=2: una sola página alcanza.
    repos = a.tendencias(7, date(2026, 10, 26), lenguaje="python", cantidad=2)
    assert [r.nombre for r in repos] == ["ana/rapido", "beto/nuevo"]
    repos = a.buscar(Q, cantidad=2)
    # Dos llamadas → exactamente dos pedidos (ninguno extra), todos con UA identificable.
    assert len(pedidos) == 2 and all(ua.startswith("py100-github_tendencias/") for _, ua in pedidos)
    # Caso borde: más del tope de 1000 de la búsqueda.
    with pytest.raises(ValueError):
        a.buscar(Q, cantidad=5000)


def test_tres_paginas_y_fin(servidor):
    # (Pese al nombre, se piden 2 páginas: la segunda viene incompleta y corta la paginación.)
    j = lambda n: (200, "application/json", (FX / n).read_bytes())
    base, pedidos = servidor({ruta(Q, 1): j("pagina1.json"), ruta(Q, 2): j("pagina2.json")})
    # Con per_page=2 y cantidad=10: página 1 (2 items), página 2 (1 item < 2) → corta.
    a = ApiGitHub(ClienteEducado(intervalo=0, respetar_robots=False), base=base)
    repos = a.buscar(Q, cantidad=10, por_pagina=2)
    assert [r.nombre for r in repos] == ["ana/rapido", "beto/nuevo", "caro/lento"] and len(pedidos) == 2
    # caro/lento trae language y description null → valores por defecto.
    assert repos[2].lenguaje == "—" and repos[2].descripcion == ""


def test_token_y_cabeceras():
    vistas = []

    def fetcher(url, cab):
        """Fetcher falso: registra las cabeceras y responde una búsqueda vacía."""
        vistas.append(cab)
        return Respuesta(200, {}, b'{"items": []}', url)

    ApiGitHub(ClienteEducado(fetcher=fetcher, intervalo=0, respetar_robots=False), token="t0k").buscar(Q, 5)
    assert vistas[0]["Authorization"] == "Bearer t0k" and vistas[0]["Accept"] == "application/vnd.github+json"


def test_rate_limit():
    def fetcher(url, cab):
        """Simula el 403 de límite primario de GitHub, con timestamp de reinicio."""
        return Respuesta(403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1793016000"}, b"{}", url)

    with pytest.raises(LimiteExcedido) as e:
        ApiGitHub(ClienteEducado(fetcher=fetcher, intervalo=0, respetar_robots=False)).buscar(Q)
    # El timestamp Unix se convierte a datetime UTC.
    assert e.value.reinicio == datetime.fromtimestamp(1793016000, timezone.utc)
    # La CLI lo traduce al exit code 4.
    rc = ejecutar([], ApiGitHub(ClienteEducado(fetcher=fetcher, intervalo=0, respetar_robots=False)), {}, lambda: AHORA)
    assert rc == 4


def test_ranking_y_salidas(api, tmp_path):
    a, _ = api
    repos = a.buscar(Q, cantidad=2)
    # ana: 900/6.5 días ≈ 138.5; beto: 500 en 1 día (mínimo) = 500 → beto primero
    assert [r.nombre for r in ordenar_por_ritmo(repos, AHORA)] == ["beto/nuevo", "ana/rapido"]
    md = markdown(repos, AHORA)
    # Enlace al repo y '|' de la descripción escapado para no romper la tabla.
    assert "[ana/rapido](https://github.com/ana/rapido)" in md and "Tiene \\| barra" in md
    filas = list(csv.DictReader(exportar_csv(repos, tmp_path / "r.csv", AHORA).open()))
    assert filas[0]["estrellas_por_dia"] == "138.5" and filas[0]["temas"] == "demo"


def test_cli(api, tmp_path, capsys):
    a, _ = api
    salida = tmp_path / "t.csv"
    assert ejecutar(["--lenguaje", "python", "--cantidad", "2", "--ritmo", "--csv", str(salida)], a, {}, lambda: AHORA) == 0
    out = capsys.readouterr().out
    # Línea 2 = primera fila de datos (tras encabezado y separador): con --ritmo gana beto.
    assert out.splitlines()[2].startswith("| 1 | [beto/nuevo]") and salida.exists()
    assert ejecutar(["--lenguaje", "rust"], a, {}, lambda: AHORA) == 1          # 404 en el servidor local
