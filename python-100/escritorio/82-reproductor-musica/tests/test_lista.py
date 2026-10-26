"""Tests de la lista de reproducción."""
from pathlib import Path

import pytest

from reproductor.lista import ListaReproduccion, Repetir, escanear

P = [Path(f"{c}.mp3") for c in "abcd"]


def test_navegacion_y_fin():
    """Con 4 pistas: avanzar 3 veces llega a d; el avance automático sin repetición termina
    (None), pero el manual da la vuelta a a, y anterior desde a vuelve a d.
    """
    l = ListaReproduccion(P)
    assert l.actual.name == "a.mp3"
    assert [l.siguiente().name for _ in range(3)] == ["b.mp3", "c.mp3", "d.mp3"]
    assert l.siguiente(automatico=True) is None       # fin sin repetición
    assert l.siguiente().name == "a.mp3"             # manual: vuelve al inicio
    assert l.anterior().name == "d.mp3"


def test_repetir():
    """Repetir UNA: el avance automático repite a, el manual pasa a b. Repetir TODAS: desde b
    (la última de 2) el automático vuelve a a.
    """
    l = ListaReproduccion(P[:2])
    l.repetir = Repetir.UNA
    assert l.siguiente(automatico=True).name == "a.mp3"
    assert l.siguiente().name == "b.mp3"              # manual ignora "una"
    l.repetir = Repetir.TODAS
    assert l.siguiente(automatico=True).name == "a.mp3"


def test_aleatorio_reproducible_y_conserva_actual():
    """Misma semilla → mismo barajado. Al activar aleatorio, la pista actual (b, índice 1)
    queda primera para no cortar lo que suena; el orden sigue siendo una permutación de
    0..3. Al desactivar vuelve el orden original y la actual sigue siendo b.
    """
    a, b = ListaReproduccion(P, semilla=1), ListaReproduccion(P, semilla=1)
    a.siguiente(); b.siguiente()                      # actual = b
    a.alternar_aleatorio(); b.alternar_aleatorio()
    assert a.orden == b.orden and a.orden[0] == 1
    assert sorted(a.orden) == [0, 1, 2, 3]
    a.alternar_aleatorio()
    assert a.orden == [0, 1, 2, 3] and a.actual.name == "b.mp3"


@pytest.mark.parametrize("quitar, esperado", [(0, "c.mp3"), (3, "c.mp3"), (2, "d.mp3")])
def test_quitar_ajusta_posicion(quitar, esperado):
    """Con c sonando (posición 2) sobre a, b, c, d: quitar una pista anterior (0) corre la
    posición una lugar atrás para seguir en c; quitar una posterior (3) no la toca; quitar
    la actual (2) deja como actual a la que ocupaba su lugar (d). Siempre quedan 3.
    """
    l = ListaReproduccion(P)
    l.ir_a(2)                                         # actual = c
    l.quitar(quitar)
    assert l.actual.name == esperado and len(l) == 3


def test_vacia_y_agregar():
    """Lista vacía: actual y siguiente dan None. Agregar la deja como actual. Quitar un índice
    inexistente lanza IndexError.
    """
    l = ListaReproduccion()
    assert l.actual is None and l.siguiente() is None
    l.agregar(Path("x.ogg"))
    assert l.actual.name == "x.ogg"
    with pytest.raises(IndexError):
        l.quitar(5)


def test_escanear(tmp_path):
    """Busca recursivamente solo extensiones de audio (sin importar mayúsculas), ignora .txt y
    ordena por nombre sin distinguir mayúsculas: a.OGG, B.mp3, c.wav.
    """
    (tmp_path / "sub").mkdir()
    for n in ("B.mp3", "a.OGG", "sub/c.wav", "nota.txt"):
        (tmp_path / n).write_bytes(b"")
    assert [p.name for p in escanear(tmp_path)] == ["a.OGG", "B.mp3", "c.wav"]
