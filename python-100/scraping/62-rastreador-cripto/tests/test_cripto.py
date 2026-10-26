"""Tests: API simulada en 127.0.0.1 con fixtures JSON."""
from datetime import datetime, timezone
from pathlib import Path

from cripto import ApiCoinGecko, Cotizacion, Historial, ReglaVariacion, evaluar
from cripto.cli import ejecutar
from cripto.cliente import ClienteEducado

# Respuestas JSON de ejemplo: precios1 (base) y precios2 (bitcoin +6 %).
FX = Path(__file__).parent / "fixtures"
# Ruta exacta (con la query codificada) que debe pedir el cliente.
Q = "/api/v3/simple/price?ids=bitcoin%2Cethereum%2Cnoexiste&vs_currencies=usd&include_24hr_change=true&include_last_updated_at=true"
# Momento fijo para las cotizaciones armadas a mano.
T = datetime(2026, 10, 26, tzinfo=timezone.utc)



def api_local(servidor, fixture="precios1.json"):
    """API apuntada a un servidor local que sirve el fixture pedido."""
    base, pedidos = servidor({Q: (200, "application/json", (FX / fixture).read_bytes())})
    return ApiCoinGecko(ClienteEducado(intervalo=0), base + "/api/v3", clave_api="demo"), pedidos


# "noexiste" se omite sin error; se pidió robots.txt primero y con nuestro User-Agent.
def test_api_parsea_y_omite_inexistentes(servidor):
    api, pedidos = api_local(servidor)
    cots = api.precios(["bitcoin", "ethereum", "noexiste"])
    assert [(c.moneda, c.precio) for c in cots] == [("bitcoin", 60000.0), ("ethereum", 3000.0)]
    assert cots[1].cambio_24h == -7.25 and cots[0].momento.year == 2026
    assert pedidos[0][0] == "/robots.txt" and pedidos[1][1].startswith("py100-cripto/")


# +6 % supera el 5 %, cruza 104 hacia arriba y el 24 h (12 %) supera 10; +2 % no dispara nada.
def test_evaluar_reglas():
    ant = Cotizacion("btc", 100.0, "usd", None, T)
    regla = ReglaVariacion(5, precio_mayor=104, precio_menor=90, umbral_24h=10)
    msgs = [a.mensaje for a in evaluar(Cotizacion("btc", 106.0, "usd", 12.0, T), ant, regla)]
    assert msgs[0].startswith("▲ btc +6.00%") and "superó 104" in msgs[1] and "+12.00% en 24 h" in msgs[2]
    assert evaluar(Cotizacion("btc", 102.0, "usd", 1.0, T), ant, regla) == []
    # ya estaba por encima: no se repite el aviso de cruce
    assert not any("superó" in a.mensaje for a in evaluar(Cotizacion("btc", 110, "usd", None, T),
                                                          Cotizacion("btc", 108, "usd", None, T), regla))
    assert "bajó de 90" in evaluar(Cotizacion("btc", 89, "usd", None, T), ant, ReglaVariacion(50, precio_menor=90))[0].mensaje


# Sin archivo no hay última lectura; después de dos agregados la última es la de precio 2.
def test_historial(tmp_path):
    h = Historial(tmp_path / "h.csv")
    assert h.ultima("btc", "usd") is None
    h.agregar([Cotizacion("btc", 1.0, "usd", None, T)]); h.agregar([Cotizacion("btc", 2.0, "usd", 0.5, T)])
    assert h.ultima("btc", "usd").precio == 2.0 and len(h.leer()) == 2


# Primera ejecución sin historial (sin alertas); la segunda ve +6 % en bitcoin.
def test_cli_dos_lecturas_genera_alerta(servidor, tmp_path, capsys):
    hist = tmp_path / "h.csv"
    args = ["bitcoin", "ethereum", "noexiste", "--historial", str(hist), "--umbral", "5"]
    api1, _ = api_local(servidor, "precios1.json")
    assert ejecutar(args, api1) == 0
    api2, _ = api_local(servidor, "precios2.json")
    assert ejecutar(args, api2) == 0
    out = capsys.readouterr().out
    assert "🔔 ▲ bitcoin +6.00%" in out and "ethereum" in out and "Sin datos para: noexiste" in out


# Se pidieron 5 s pero se espera el mínimo de 60 s; 2 iteraciones → 1 espera.
def test_cli_vigilar_respeta_minimo(servidor, tmp_path):
    api, _ = api_local(servidor)
    esperas = []
    assert ejecutar(["bitcoin", "ethereum", "noexiste", "--historial", str(tmp_path / "h.csv"), "--vigilar", "5"],
                    api, esperas.append, max_iter=2) == 0
    assert esperas == [60.0]


# Servidor sin la ruta de la API → 404 → ErrorHTTP → exit 1.
def test_cli_error_http(servidor, tmp_path):
    base, _ = servidor({})
    api = ApiCoinGecko(ClienteEducado(intervalo=0), base)
    assert ejecutar(["bitcoin", "--historial", str(tmp_path / "h.csv")], api) == 1
