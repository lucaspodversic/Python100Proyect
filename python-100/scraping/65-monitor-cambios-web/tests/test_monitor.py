"""Tests con servidor local mutable (127.0.0.1) y transportes falsos."""
import json

import pytest

from monitor_web import Monitor, NotificadorWebhook, Objetivo, extraer_texto
from monitor_web.cli import ejecutar
from monitor_web.cliente import ClienteEducado, Respuesta
from monitor_web.monitor import Cambio, hacer_diff

# Versión 1 de la página: incluye ruido típico (script, comentario, contador de visitas, fecha).
V1 = b"""<html><body><script>var t=123;</script><!-- c -->
<div id="precio">Precio: $100</div><p>Visitas: 541</p><footer>Hoy 2026-10-26</footer></body></html>"""
# Versión 2: cambia el precio (relevante) y el contador (ruido).
V2 = V1.replace(b"$100", b"$90").replace(b"541", b"999")


def test_extraer_texto():
    t = extraer_texto(V1.decode())
    # El <script> desaparece, el contenido visible queda.
    assert "var t" not in t and "Precio: $100" in t
    # Con selector sólo queda la región elegida.
    assert extraer_texto(V1.decode(), "#precio") == "Precio: $100"
    # Las regex de "ignorar" eliminan el ruido.
    assert "Visitas" not in extraer_texto(V1.decode(), ignorar=(r"Visitas: \d+",))
    # Caso borde: selector que no existe → error explícito, no texto vacío.
    with pytest.raises(LookupError):
        extraer_texto(V1.decode(), "#nada")


def test_diff():
    # b→B es 1 quitada + 1 agregada; 'd' es otra agregada → (2, 1).
    d, mas, menos = hacer_diff("a\nb\nc", "a\nB\nc\nd", "x")
    assert (mas, menos) == (2, 1) and "-b" in d and "+B" in d


def test_monitor_detecta_solo_cambios_relevantes(servidor, tmp_path):
    # `rutas` es el mismo dict que lee el servidor: modificarlo simula que el sitio se actualizó.
    rutas = {"/robots.txt": (200, "text/plain", b""), "/p": (200, "text/html", V1)}
    base, _ = servidor(rutas)
    vistos = []

    class N:
        """Notificador falso que sólo anota lo recibido."""
        def notificar(self, c): vistos.append(c)

    obj = Objetivo("precio", base + "/p", "#precio")
    m = Monitor([obj], tmp_path / "e.json", ClienteEducado(intervalo=0), [N()])
    assert m.revisar() == []                       # línea base
    rutas["/p"] = (200, "text/html", V1.replace(b"541", b"600"))
    assert m.revisar() == []                       # cambió algo fuera del selector
    rutas["/p"] = (200, "text/html", V2)
    cambios = m.revisar()
    # Ahora sí: un cambio, con el nuevo precio en el diff, y el notificador lo recibió.
    assert len(cambios) == 1 and "+Precio: $90" in cambios[0].diff and vistos == cambios
    # El estado persistido refleja la versión nueva (será la base de la próxima comparación).
    assert json.loads((tmp_path / "e.json").read_text())[obj.url]["texto"] == "Precio: $90"


def test_pedido_condicional_304(tmp_path):
    pedidos = []

    def fetcher(url, cab):
        """Servidor falso con ETag: si el cliente manda el ETag vigente, responde 304."""
        pedidos.append(cab)
        if url.endswith("robots.txt"):
            return Respuesta(404, {}, b"", url)
        if cab.get("If-None-Match") == '"v1"':
            return Respuesta(304, {}, b"", url)
        return Respuesta(200, {"etag": '"v1"', "content-type": "text/html"}, V1, url)

    m = Monitor([Objetivo("x", "http://s.test/p")], tmp_path / "e.json",
                ClienteEducado(fetcher=fetcher, intervalo=0, dormir=lambda s: None))
    # Dos pasadas: la primera guarda el ETag, la segunda recibe 304 → 0 cambios.
    assert m.vigilar(0, iteraciones=2, dormir=lambda s: None) == 0
    assert pedidos[-1]["If-None-Match"] == '"v1"'


def test_webhook():
    enviados = []
    # Transporte falso: decodifica el JSON enviado y devuelve 200 (`or 200` porque append devuelve None).
    n = NotificadorWebhook("https://hooks.slack.test/x", transporte=lambda u, b: enviados.append(json.loads(b)) or 200,
                           max_chars=10)
    n.notificar(Cambio("p", "http://u", "x" * 50, 1, 0, "t"))
    # Diff de 50 caracteres con tope 10 → se recorta y se avisa.
    assert "(recortado)" in enviados[0]["text"]
    # Seguridad: webhook sin https se rechaza al construir.
    with pytest.raises(ValueError):
        NotificadorWebhook("http://inseguro")
    # Un 500 del webhook es un error visible, no un fallo silencioso.
    with pytest.raises(RuntimeError):
        NotificadorWebhook("https://h", transporte=lambda u, b: 500).notificar(Cambio("p", "u", "", 0, 0, "t"))


def test_cli(servidor, tmp_path, capsys):
    rutas = {"/robots.txt": (200, "text/plain", b"User-agent: *\nDisallow: /privado\n"),
             "/p": (200, "text/html", V1)}
    base, pedidos = servidor(rutas)
    estado = tmp_path / "e.json"
    enviados = []
    # La URL contiene "discord" → la CLI debe usar el campo "content".
    args = ["--url", base + "/p", "--estado", str(estado), "--webhook", "https://discord.test/api/webhooks/1"]
    c = ClienteEducado(intervalo=0)
    # Primera corrida: línea base, sin notificaciones.
    assert ejecutar(args, c, lambda u, b: enviados.append(json.loads(b)) or 204) == 0
    rutas["/p"] = (200, "text/html", V2)
    # Segunda corrida en modo vigilancia (1 iteración, sin dormir de verdad): detecta el cambio.
    assert ejecutar(args + ["--intervalo", "1", "--iteraciones", "1"], c,
                    lambda u, b: enviados.append(json.loads(b)) or 204, dormir=lambda s: None) == 0
    assert "content" in enviados[0] and "🔔" in capsys.readouterr().out
    # Ruta prohibida por robots.txt → exit 3 y ningún pedido a esa ruta.
    assert ejecutar(["--url", base + "/privado", "--estado", str(estado)], c) == 3
    assert "/privado" not in [p for p, _ in pedidos]
