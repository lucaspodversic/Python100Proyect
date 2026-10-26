"""Tests de métricas. Los números esperados se derivan a mano de las fixtures
(ver el comentario de cada test y tests/conftest.py)."""
import json

from logweb.analisis import analizar, es_bot, es_estatico, tipo_dispositivo
from logweb.informe import a_html, a_json, a_texto, barra, humano
from logweb.parser import abrir, leer, parsear_linea


def informe_apache(apache):
    """Atajo: lee y analiza el log de Apache de ejemplo."""
    lec = leer(abrir(apache))
    return analizar(lec.registros, invalidas=lec.invalidas)


def test_totales_apache(apache):
    """16 peticiones válidas; bytes = 5120+2048+8192+1024+8000+0+512+8000+196·5+199+0+0 = 34075."""
    inf = informe_apache(apache)
    assert inf.peticiones == 16 and inf.invalidas == 1
    assert inf.bytes_totales == 34075


def test_paginas_visitas_y_visitantes(apache):
    """Páginas vistas = 6: "/", "/productos", "/contacto" (escritorio), "/productos" (iPhone),
    el 304 de "/blog/mi articulo" y el HEAD "/" (Safari). No cuentan: CSS, POST, el 500,
    el Googlebot ni las peticiones sin user-agent.
    Visitas = 4: el usuario de escritorio vuelve a las 11:00 tras 55 min (> 30) → 2 visitas,
    más 1 del iPhone y 1 del Mac. Visitantes únicos (IP+UA) = 3."""
    inf = informe_apache(apache)
    assert inf.paginas_vistas == 6 and inf.visitas == 4 and inf.visitantes_unicos == 3
    # Empate a 2 entre "/" y "/productos": se ordena alfabéticamente para ser determinista.
    assert inf.top_paginas[:2] == [("/", 2), ("/productos", 2)]
    assert ("/blog/mi articulo", 1) in inf.top_paginas  # %20 decodificado


def test_errores(apache):
    """Clases: 2xx=7, 3xx=2 (302 y 304), 4xx=6 (robots.txt + 5 del escáner), 5xx=1.
    Tasa de error = (6+1)/16 = 0.4375. El escáner (5 errores 4xx) supera el umbral de sospecha (5)."""
    inf = informe_apache(apache)
    assert inf.por_clase == {"2xx": 7, "3xx": 2, "4xx": 6, "5xx": 1}
    assert inf.tasa_error == 0.4375
    assert inf.top_404[0] == ("/wp-login.php", 2)
    assert inf.top_5xx == [("/carrito", 1)]
    assert inf.sospechosos == [("203.0.113.9", 5)]


def test_dispositivos_y_trafico_por_hora(apache):
    """bot = 2 Googlebot + 5 sin UA = 7; móvil = 3 (iPhone); escritorio = 4 Firefox + 2 Safari = 6.
    Por hora (UTC): la línea +0200 de las 12:00 cae en las 10h UTC → 15 peticiones a las 10h y 1 a las 11h."""
    inf = informe_apache(apache)
    assert inf.dispositivos == {"bot": 7, "escritorio": 6, "móvil": 3}
    assert inf.peticiones_por_hora == {"2026-10-01 10h": 15, "2026-10-01 11h": 1}
    assert sum(inf.trafico_por_hora.values()) == inf.bytes_totales
    assert inf.primera == "2026-10-01T10:00:00+00:00" and inf.ultima == "2026-10-01T11:00:00+00:00"


def test_referers_y_metodos(apache):
    """En el log de ejemplo, http://ejemplo.com/ aparece como referer 2 veces y hay 14 GET, 1
    HEAD y 1 POST (contados a mano sobre la fixture).
    """
    inf = informe_apache(apache)
    assert inf.top_referers[0] == ("http://ejemplo.com/", 2)
    assert inf.metodos == {"GET": 14, "HEAD": 1, "POST": 1}


def test_nginx(nginx):
    """Nginx: curl es bot; la imagen no es página; el 502 no es página → páginas = 3
    (/, /precios Android, /precios IPv6). Android: 08:00:10 y 08:45 (> 30 min) → 2 visitas + 1 = 3.
    08:00 -0300 = 11h UTC."""
    lec = leer(abrir(nginx))
    inf = analizar(lec.registros)
    assert inf.paginas_vistas == 3 and inf.visitas == 3 and inf.visitantes_unicos == 2
    assert inf.top_5xx == [("/precios", 1)]
    assert next(iter(inf.peticiones_por_hora)) == "2026-10-02 11h"


def test_vacio():
    """Sin registros no hay división por cero y el texto lo dice."""
    inf = analizar([], invalidas=3)
    assert inf.peticiones == 0 and inf.tasa_error == 0
    assert "Sin peticiones" in a_texto(inf)


def test_clasificadores():
    """Sin user-agent cuenta como bot; python-requests es bot y Firefox no. La extensión se
    compara sin mayúsculas. Android + Mobile → móvil.
    """
    assert es_bot(None) and es_bot("python-requests/2.31") and not es_bot("Mozilla/5.0 Firefox")
    assert es_estatico("/a/b.CSS") and not es_estatico("/productos")
    assert tipo_dispositivo("Mozilla/5.0 (Linux; Android 14) Mobile") == "móvil"


def test_formatos_de_salida(apache):
    """Texto con secciones, JSON válido con claves de estado como string, y helpers de formato."""
    inf = informe_apache(apache)
    txt = a_texto(inf)
    assert "Páginas vistas: 6" in txt and "IPs sospechosas" in txt and "█" in txt
    d = json.loads(a_json(inf))
    assert d["por_estado"]["404"] == 5 and d["visitas"] == 4
    assert humano(500) == "500 B" and humano(1536) == "1.5 KiB" and humano(3 * 1024 ** 3) == "3.0 GiB"
    assert barra(5, 10, 10) == "█" * 5 and barra(1, 0) == ""


def test_html_escapa_contenido_del_log():
    """Rutas del log las controla cualquiera que haga una petición: deben escaparse (anti-XSS)."""
    r = parsear_linea('1.1.1.1 - - [01/Jan/2026:00:00:00 +0000] "GET /<script>alert(1)</script> HTTP/1.1" '
                      '200 1 "-" "Mozilla/5.0 Firefox"')
    html = a_html(analizar([r]))
    assert "<script>alert" not in html and "&lt;script&gt;" in html
