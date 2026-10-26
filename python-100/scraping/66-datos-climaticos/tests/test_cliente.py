"""Tests del cliente educado con un fetcher falso en memoria (sin red)."""
import pytest

from clima.cliente import BloqueadoPorRobots, ClienteEducado, ErrorHTTP, Respuesta

# robots.txt de prueba: prohíbe /privado y pide 2 s entre pedidos.
ROBOTS = b"User-agent: *\nDisallow: /privado\nCrawl-delay: 2\n"


class FetcherFalso:
    """Transporte en memoria: devuelve páginas predefinidas y anota cada pedido (URL, User-Agent)."""

    def __init__(self, paginas):
        self.paginas, self.pedidos = paginas, []

    def __call__(self, url, cabeceras):
        self.pedidos.append((url, cabeceras["User-Agent"]))
        # Cualquier URL no registrada responde 404 (como un sitio sin robots.txt).
        estado, cuerpo = self.paginas.get(url, (404, b""))
        return Respuesta(estado, {"content-type": "text/html; charset=utf-8"}, cuerpo, url)


def test_robots_rate_limit_y_user_agent():
    f = FetcherFalso({"http://s.test/robots.txt": (200, ROBOTS), "http://s.test/a": (200, b"ok")})
    # Reloj congelado en 0: así toda espera calculada es completa y determinista.
    reloj, esperas = [0.0], []
    c = ClienteEducado(fetcher=f, intervalo=0.5, reloj=lambda: reloj[0], dormir=esperas.append)
    assert c.get("http://s.test/a").texto() == "ok"
    # Ruta prohibida: debe fallar sin generar un pedido.
    with pytest.raises(BloqueadoPorRobots):
        c.get("http://s.test/privado/x")
    assert [u for u, _ in f.pedidos] == ["http://s.test/robots.txt", "http://s.test/a"]  # lo prohibido no se pidió
    assert esperas == [2.0]                # el Crawl-delay (2 s) manda sobre el intervalo (0.5 s)
    assert "Mozilla" not in f.pedidos[0][1]   # nunca se disfraza de navegador


def test_errores():
    f = FetcherFalso({"http://s.test/x": (500, b"")})
    c = ClienteEducado(fetcher=f, intervalo=0, dormir=lambda s: None)
    with pytest.raises(ErrorHTTP):
        c.get("http://s.test/x")          # sin robots.txt (404) → permitido, pero 500
    with pytest.raises(ValueError):
        c.get("file:///etc/passwd")       # caso borde de seguridad: esquemas no HTTP se rechazan
