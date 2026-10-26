"""Tests de métricas (fixtures), reglas (reloj falso) y webhooks (servidor local)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from monitor import (EvaluadorAlertas, Metricas, NotificadorDiscord, NotificadorSlack,
                     ProveedorLinux, TransporteHTTP, Umbrales)
from monitor.bot import ciclo
from monitor.metricas import uso_cpu, uso_memoria

# Carpeta con copias falsas de /proc/stat y /proc/meminfo.
FIX = Path(__file__).parent / "fixtures"


def test_uso_cpu():
    # Entre lecturas: total +100, idle +25 → 75% ocupada
    assert uso_cpu("cpu 100 0 100 800 0", "cpu 150 0 125 825 0") == 75.0
    # Lecturas idénticas: delta 0 → 0 %.
    assert uso_cpu("cpu 1 1 1 1", "cpu 1 1 1 1") == 0.0


# Fixture: MemTotal 1000, MemAvailable 250 → 1 - 250/1000 = 75 %.
def test_uso_memoria():
    assert uso_memoria((FIX / "meminfo").read_text()) == 75.0
    assert uso_memoria("") == 0.0


# Mismo stat leído dos veces (CPU 0 %); el disco es el real, sólo se verifica el rango.
def test_proveedor_linux_con_fixture():
    m = ProveedorLinux(FIX, "/", intervalo=0).leer()
    assert m.cpu == 0.0 and m.memoria == 75.0 and 0 <= m.disco <= 100


# Reloj manual: el test decide cuánto tiempo "pasó".
class Reloj:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t


def test_consecutivas_enfriamiento_y_recuperacion():
    reloj = Reloj()
    # Umbral 80 %, 2 lecturas consecutivas y 100 s de enfriamiento.
    ev = EvaluadorAlertas(Umbrales(cpu=80, lecturas_consecutivas=2, enfriamiento_seg=100), reloj)
    alto, normal = Metricas(95, 10, 10), Metricas(10, 10, 10)
    assert ev.evaluar(alto) == []               # 1ª lectura: todavía no
    a = ev.evaluar(alto)
    assert len(a) == 1 and a[0].metrica == "cpu"  # 2ª: alerta
    reloj.t = 50
    assert ev.evaluar(alto) == []               # en enfriamiento
    reloj.t = 200
    assert len(ev.evaluar(alto)) == 1           # enfriado: repite
    r = ev.evaluar(normal)
    assert r[0].recuperada and "normalizada" in r[0].texto("srv")


# Guarda los envíos en memoria y devuelve el código pedido.
class TransporteFalso:
    def __init__(self, status=200): self.envios, self.status = [], status
    def post_json(self, url, cuerpo): self.envios.append((url, cuerpo)); return self.status


# Slack usa "text"; Discord usa "content" recortado a 2000 caracteres.
def test_formatos_webhook():
    t = TransporteFalso()
    assert NotificadorSlack("https://hooks.slack.com/x", t).enviar("hola")
    assert NotificadorDiscord("https://discord.com/api/webhooks/x", t).enviar("y" * 3000)
    assert t.envios[0][1] == {"text": "hola"}
    assert len(t.envios[1][1]["content"]) == 2000


# Proveedor que siempre devuelve 99 % en todo.
class ProvFijo:
    def leer(self): return Metricas(99, 99, 99)


# Un canal que lanza excepción no impide que el otro reciba las 3 alertas.
def test_ciclo_tolera_canal_caido():
    class Roto:
        def enviar(self, t): raise ConnectionError("caído")
    ok = NotificadorSlack("https://x", TransporteFalso())
    ev = EvaluadorAlertas(Umbrales(lecturas_consecutivas=1))
    assert ciclo(ProvFijo(), ev, [Roto(), ok], "srv") == 3  # 3 métricas en alerta, sólo 'ok' cuenta


# Servidor HTTP local efímero: prueba urllib de verdad sin salir de la máquina.
def test_transporte_http_real_contra_localhost():
    recibidos = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            recibidos.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(204); self.end_headers()
        def log_message(self, *a): pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.server_port}/hook"
        assert NotificadorSlack(url, TransporteHTTP()).enviar("test")
        assert recibidos == [{"text": "test"}]
    finally:
        srv.shutdown(); srv.server_close()


# HTTP sin cifrar hacia un host externo se rechaza antes de conectar.
def test_transporte_rechaza_http_externo():
    with pytest.raises(ValueError):
        TransporteHTTP().post_json("http://ejemplo.com/hook", {})
