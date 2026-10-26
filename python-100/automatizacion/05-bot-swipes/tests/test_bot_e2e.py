"""Flujo completo contra la app mock local (127.0.0.1)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from bot_swipes.bot import BotSwipes
from bot_swipes.cli import main
from bot_swipes.navegador import HttpNavegador
from bot_swipes.preferencias import Preferencias
from bot_swipes.sitio_mock import EstadoApp, iniciar

# Edad 25-35, hasta 20 km, intereses senderismo/cine (mínimo 1 en común), excluye "fumador".
PREF = Preferencias(25, 35, 20, ["senderismo", "cine"], 1, ["fumador"])


# App mock nueva por test: el estado de swipes arranca vacío.
@pytest.fixture()
def app() -> Iterator[tuple[str, EstadoApp]]:
    srv, estado = iniciar()
    yield f"http://127.0.0.1:{srv.server_address[1]}/perfiles", estado
    srv.shutdown()


def test_recorre_todos_los_perfiles(app: tuple[str, EstadoApp]) -> None:
    url, estado = app
    pausas: list[float] = []
    # Resultado esperado perfil por perfil (ver PERFILES_DEMO):
    #   p1 29 años, 5 km, senderismo+cine → like · p2 45 años → pass (edad)
    #   p3 120 km → pass (distancia) · p4 27 años, cine, sin bio (no se exige) → like
    #   p5 bio "Fumador social" → pass · p6 "Senderismo" en mayúsculas → like.
    hist = BotSwipes(HttpNavegador(), PREF, url, dry_run=False, pausa=1.5, dormir=pausas.append).ejecutar()
    assert [(s.perfil.id, s.veredicto.like) for s in hist] == [
        ("p1", True), ("p2", False), ("p3", False), ("p4", True), ("p5", False), ("p6", True)]
    assert estado.swipes == [("p1", "like"), ("p2", "pass"), ("p3", "pass"),
                             ("p4", "like"), ("p5", "pass"), ("p6", "like")]
    # p3 también tiene match=True en el mock, pero recibió pass: el único match es p1.
    assert [s.perfil.id for s in hist if s.match] == ["p1"]
    # Una pausa por cada uno de los 6 swipes ejecutados.
    assert pausas == [1.5] * 6


def test_dry_run_no_swipea(app: tuple[str, EstadoApp]) -> None:
    url, estado = app
    hist = BotSwipes(HttpNavegador(), PREF, url, dry_run=True, dormir=lambda s: None).ejecutar()
    # Dry-run: evalúa sólo el primer perfil y el servidor no recibe ningún swipe.
    assert len(hist) == 1 and not hist[0].ejecutado and estado.swipes == []


def test_limite_de_likes(app: tuple[str, EstadoApp]) -> None:
    url, estado = app
    # max_likes=1: like a p1, pass a p2 y p3; al llegar a p4 (que sería like) el bot se detiene
    # en lugar de pasarlo, por eso p4 no aparece en los swipes del servidor.
    hist = BotSwipes(HttpNavegador(), PREF, url, dry_run=False, max_likes=1, pausa=0, dormir=lambda s: None).ejecutar()
    assert sum(s.veredicto.like for s in hist) == 1
    assert estado.swipes == [("p1", "like"), ("p2", "pass"), ("p3", "pass")]


def test_rechaza_urls_reales() -> None:
    with pytest.raises(ValueError):
        # Una URL de una app real se rechaza al construir el bot, antes de cualquier petición.
        BotSwipes(HttpNavegador(), PREF, "https://tinder.com/app/recs")


def test_cli(capsys: pytest.CaptureFixture[str]) -> None:
    # Con --swipear la CLI da like a p1, que tiene match predefinido → aparece "MATCH".
    assert main(["--edad", "25", "35", "--interes", "cine", "--swipear", "--pausa", "0"]) == 0
    assert "MATCH" in capsys.readouterr().out
