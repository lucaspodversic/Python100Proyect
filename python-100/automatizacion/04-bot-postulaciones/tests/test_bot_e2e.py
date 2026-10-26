"""Tests end-to-end contra el sitio MOCK local (127.0.0.1) con HttpNavegador."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from bot_postulaciones.bot import BotPostulaciones, Registro, validar_url_local
from bot_postulaciones.cli import main
from bot_postulaciones.navegador import HttpNavegador, SeleniumNavegador
from bot_postulaciones.perfil import Perfil
from bot_postulaciones.sitio_mock import EstadoSitio, iniciar

RAIZ = Path(__file__).resolve().parents[1]


# Un sitio mock NUEVO por test (scope función): cada test arranca sin postulaciones previas.
@pytest.fixture()
def sitio() -> Iterator[tuple[str, EstadoSitio]]:
    srv, estado = iniciar()
    yield f"http://127.0.0.1:{srv.server_address[1]}/ofertas", estado
    srv.shutdown()


def perfil() -> Perfil:
    return Perfil(**json.loads((RAIZ / "perfil.ejemplo.json").read_text(encoding="utf-8")))


def test_dry_run_no_postula(sitio: tuple[str, EstadoSitio]) -> None:
    url, estado = sitio
    # De dónde salen los números con perfil.ejemplo.json (obligatoria "python", excluidas
    # "guardias"/"trainee", ubicación Buenos Aires, mínimo 2500):
    #   101 remoto Python+Django+Docker → aplica · 102 Java, falta "python" → no
    #   103 contiene "Guardias" → no · 104 Buenos Aires, Python/FastAPI → aplica
    #   105 React, falta "python" → no · 106 "Trainee" → no.
    # Las 6 ofertas están repartidas en 2 páginas de 3.
    res = BotPostulaciones(HttpNavegador(), perfil(), url, dry_run=True, pausa=0, dormir=lambda s: None).ejecutar()
    assert len(res) == 6  # recorrió las dos páginas
    assert {r.oferta.id for r in res if r.decision.aplicar} == {"101", "104"}
    assert estado.postulaciones == []


def test_postula_respetando_limites_y_registro(sitio: tuple[str, EstadoSitio]) -> None:
    url, estado = sitio
    pausas: list[float] = []
    # Registro compartido entre las dos corridas, para probar la idempotencia.
    reg = Registro()
    bot = BotPostulaciones(HttpNavegador(), perfil(), url, dry_run=False, max_postulaciones=1,
                           pausa=2.0, registro=reg, dormir=pausas.append)
    # max_postulaciones=1: se postula a la primera apta (101) y se corta.
    res = bot.ejecutar()
    assert [r.oferta.id for r in res if r.postulado] == ["101"]
    assert estado.postulaciones[0]["nombre"] == "Candidato Demo"
    assert estado.postulaciones[0]["token"] == "demo"  # campos ocultos se envían
    # Todas las pausas pedidas usan el valor configurado.
    assert pausas and all(p == 2.0 for p in pausas)
    # Segunda corrida: 101 ya está registrada, se postula a la siguiente (104).
    res2 = BotPostulaciones(HttpNavegador(), perfil(), url, dry_run=False, max_postulaciones=5, pausa=0,
                            registro=reg, dormir=lambda s: None).ejecutar()
    assert [r.oferta.id for r in res2 if r.postulado] == ["104"]
    assert len(estado.postulaciones) == 2


def test_solo_urls_locales() -> None:
    # localhost pasa; cualquier dominio real (aunque sea .example) se rechaza con ValueError.
    validar_url_local("http://localhost:8000/x")
    with pytest.raises(ValueError):
        validar_url_local("https://www.linkedin.com/jobs")
    with pytest.raises(ValueError):
        BotPostulaciones(HttpNavegador(), perfil(), "https://portal-real.example/ofertas")


def test_cli_levanta_mock_y_corre(capsys: pytest.CaptureFixture[str]) -> None:
    # La CLI sin --url levanta su propio mock y corre en dry-run (por eso imprime "APLICARÍA").
    assert main(["--perfil", str(RAIZ / "perfil.ejemplo.json"), "--pausa", "0"]) == 0
    salida = capsys.readouterr().out
    assert "APLICARÍA" in salida and "descartada" in salida


# Doble de prueba con la API de selenium.WebElement (text, get_attribute, click, clear, send_keys).
class _WebElementFalso:
    def __init__(self) -> None:
        self.text, self.acciones = "Hola", []

    def get_attribute(self, n: str) -> str:
        return f"attr-{n}"

    def click(self) -> None:
        self.acciones.append("click")

    def clear(self) -> None:
        self.acciones.append("clear")

    def send_keys(self, v: str) -> None:
        self.acciones.append(f"keys:{v}")


# Doble de WebDriver: verifica además que el adaptador use el localizador "css selector".
class _DriverFalso:
    def __init__(self) -> None:
        self.current_url, self.el = "", _WebElementFalso()

    def get(self, url: str) -> None:
        self.current_url = url

    def find_elements(self, by: str, sel: str) -> list[_WebElementFalso]:
        assert by == "css selector"
        return [self.el]


def test_adaptador_selenium_con_driver_falso() -> None:
    d = _DriverFalso()
    nav = SeleniumNavegador(d)
    nav.ir("http://127.0.0.1/x")
    el = nav.buscar("a")[0]
    el.clic()
    el.escribir("abc")
    assert nav.url_actual == "http://127.0.0.1/x" and el.texto == "Hola"
    # ``escribir`` debe limpiar antes de tipear: por eso "clear" aparece antes de "keys:abc".
    assert el.atributo("href") == "attr-href" and d.el.acciones == ["click", "clear", "keys:abc"]
