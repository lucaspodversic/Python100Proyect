"""Tests de humo de la capa pygame, con drivers "dummy" de SDL (sin ventana ni audio reales)."""
import os

import pytest

from juegos.pong import Pong
from juegos.snake import Snake
from juegos.ventana import CELDA, VERDE, dibujar_pong, dibujar_snake, main


@pytest.fixture()
def pg(monkeypatch):
    """pygame inicializado con drivers dummy (se saltea si pygame no está instalado).

    Los drivers dummy permiten crear superficies y "ventanas" en memoria: los
    tests corren igual en CI sin DISPLAY.
    """
    pygame = pytest.importorskip("pygame")
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    yield pygame
    pygame.quit()


def test_importable_sin_pygame_inicializado():
    """Importar el módulo no abre ventanas ni requiere display."""
    import juegos.ventana  # noqa: F401


def test_dibujar_snake(pg):
    """El píxel del centro de la cabeza (10,7) queda pintado de VERDE."""
    j = Snake(semilla=1)
    sup = pg.Surface((j.ancho * CELDA, j.alto * CELDA))
    dibujar_snake(sup, j, pg.font.Font(None, 20))
    assert tuple(sup.get_at((10 * CELDA + CELDA // 2, 7 * CELDA + CELDA // 2)))[:3] == VERDE


def test_dibujar_pong(pg):
    """La pelota (blanca) está en el centro del campo al inicio."""
    j = Pong(semilla=1)
    sup = pg.Surface((640, 400))
    dibujar_pong(sup, j, pg.font.Font(None, 30))
    assert tuple(sup.get_at((320, 200)))[:3] == (235, 235, 235)


def test_bucles_cortos(pg):
    """Los bucles principales corren unos cuadros con el driver dummy y salen con código 0."""
    from juegos.ventana import correr_pong, correr_snake
    assert correr_snake(semilla=1, max_cuadros=3) == 0
    assert correr_pong(semilla=1, max_cuadros=3) == 0


def test_cli_requiere_subcomando():
    """Sin subcomando (snake/pong) argparse termina con SystemExit (código 2)."""
    with pytest.raises(SystemExit):
        main([])
