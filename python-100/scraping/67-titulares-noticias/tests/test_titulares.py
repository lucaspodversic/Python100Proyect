"""Tests con feeds locales, servidor 127.0.0.1 y SMTP falso."""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from titulares import EnviadorSMTP, agregar, armar_mensaje, filtrar, html_resumen, parsear_feed
from titulares.cli import ejecutar
from titulares.cliente import ClienteEducado
from titulares.feeds import Noticia

FX = Path(__file__).parent / "fixtures"
# "Ahora" fijo para que los filtros por antigüedad sean deterministas.
AHORA = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)


def test_rss_y_atom():
    rss = parsear_feed((FX / "rss.xml").read_bytes())
    # La descripción traía HTML escapado (&lt;p&gt;…): queda texto plano.
    assert rss[0].fuente == "Diario Ejemplo" and rss[0].resumen == "Nuevos paneles más eficientes"
    assert rss[0].fecha == datetime(2026, 10, 26, 9, tzinfo=timezone.utc)
    atom = parsear_feed((FX / "atom.xml").read_bytes())
    # La entrada tiene un link rel="self" primero: debe elegirse el alternate.
    assert atom[0].enlace == "https://blog.test/py314" and atom[0].fuente == "Blog Tech"


def test_rechaza_entidades():
    # Caso borde de seguridad: DOCTYPE con ENTITY → rechazado antes de parsear.
    malo = b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "x">]><rss><channel></channel></rss>'
    with pytest.raises(ValueError):
        parsear_feed(malo)
    # XML válido pero que no es un feed.
    with pytest.raises(ValueError):
        parsear_feed(b"<html></html>")


def test_agregar_y_filtrar():
    todas = agregar([parsear_feed((FX / "rss.xml").read_bytes()), parsear_feed((FX / "atom.xml").read_bytes())])
    # Orden por fecha descendente, mezclando ambos feeds.
    assert [n.titulo for n in todas][:2] == ["Python 3.14 publicado", "Avances en energía solar"]
    assert len(todas) == 4                                     # el duplicado en mayúsculas se descarta
    # "ENERGIA" (sin tilde, mayúsculas) coincide con "energía".
    assert [n.titulo for n in filtrar(todas, ["ENERGIA"])] == ["Avances en energía solar"]
    assert len(filtrar(todas, excluir=["partido"])) == 3
    # La noticia del 20/10 queda fuera del corte del 25/10.
    assert len(filtrar(todas, desde=datetime(2026, 10, 25, tzinfo=timezone.utc))) == 3


def test_html_escapa():
    # Un título malicioso no debe inyectar HTML en el email.
    h = html_resumen([Noticia("<script>x</script>", "https://a?b=1&c=2", "F", None)])
    assert "<script>" not in h and "&amp;c=2" in h


def test_smtp_falso():
    eventos = []

    class SMTPFalso:
        """Imita la interfaz de smtplib.SMTP y registra el orden de las llamadas."""
        def __init__(self, host, puerto, timeout): eventos.append(("con", host, puerto))
        def __enter__(self): return self
        def __exit__(self, *a): eventos.append(("fin",))
        def starttls(self, context): eventos.append(("tls",))
        def login(self, u, c): eventos.append(("login", u))
        def send_message(self, m): eventos.append(("envio", m["To"]))

    m = armar_mensaje("yo@x.test", ["a@x.test", "b@x.test"], "Asunto", "hola", "<b>hola</b>")
    EnviadorSMTP("smtp.x.test", 587, "yo", "secreto", fabrica=SMTPFalso).enviar(m)
    # Orden crítico: TLS antes del login (la clave nunca viaja en claro) y cierre al final.
    assert eventos == [("con", "smtp.x.test", 587), ("tls",), ("login", "yo"), ("envio", "a@x.test, b@x.test"), ("fin",)]


def test_cli(servidor, capsys):
    base, pedidos = servidor({"/robots.txt": (200, "text/plain", b""),
                              "/rss": (200, "application/rss+xml", (FX / "rss.xml").read_bytes()),
                              "/atom": (200, "application/atom+xml", (FX / "atom.xml").read_bytes())})
    c = ClienteEducado(intervalo=0)
    # Un feed caído (/caido → 404) no impide el resumen de los otros dos.
    assert ejecutar([base + "/rss", base + "/atom", base + "/caido", "--horas", "24"], c, ahora=lambda: AHORA) == 0
    captura = capsys.readouterr()
    assert "1. Python 3.14 publicado" in captura.out and "vieja" not in captura.out and "/caido" in captura.err
    enviados = []

    class Fake:
        """Enviador falso: guarda el mensaje en vez de mandarlo."""
        def enviar(self, m): enviados.append(m)

    assert ejecutar([base + "/rss", "--email", "a@x.test"], c, Fake(), {}, lambda: AHORA) == 0
    # Asunto con fecha y cantidad; el mensaje incluye la parte HTML.
    assert enviados[0]["Subject"] == "Titulares 26/10/2026 (3)" and enviados[0].get_body(("html",))
    # Sin enviador y sin SMTP_HOST en el entorno → exit 1 (no intenta conectar a nada).
    assert ejecutar([base + "/rss", "--email", "a@x.test"], c, None, {}, lambda: AHORA) == 1
    # Todos los feeds fallaron → exit 2.
    assert ejecutar([base + "/caido"], c) == 2
