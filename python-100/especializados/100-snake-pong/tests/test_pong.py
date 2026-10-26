"""Tests de la física de Pong (sin pygame). Campo 640x400, paletas de 10x70 en x=20 y x=610."""
import math

import pytest

from juegos.pong import ACELERACION, EventoPong, Pong, ia


def con_pelota(j: Pong, x, y, vx, vy) -> Pong:
    """Coloca la pelota a mano para escenarios exactos."""
    j.pelota.x, j.pelota.y, j.pelota.vx, j.pelota.vy = x, y, vx, vy
    return j


def test_saque_determinista():
    """Saque desde el centro, a 300 px/s, con ángulo ≤ 30°; misma semilla → mismo saque."""
    a, b = Pong(semilla=3), Pong(semilla=3)
    assert (a.pelota.vx, a.pelota.vy) == (b.pelota.vx, b.pelota.vy)
    assert (a.pelota.x, a.pelota.y) == (320, 200)
    assert math.hypot(a.pelota.vx, a.pelota.vy) == pytest.approx(300)
    assert abs(a.pelota.vy) <= 300 * math.sin(math.radians(30)) + 1e-9


def test_rebote_en_techo():
    """Pelota subiendo cerca del techo: vy cambia de signo y la pelota queda dentro del campo."""
    j = con_pelota(Pong(semilla=1), 320, 8, 0, -300)
    ev = j.actualizar(0.05)
    assert EventoPong.REBOTE_PARED in ev and j.pelota.vy > 0 and j.pelota.y >= j.pelota.radio


def test_golpe_centrado_sale_recto_y_acelera():
    """Impacto en el centro de la paleta izquierda (y=200): ángulo 0 → vy = 0, vx > 0, rapidez ×1.05."""
    j = con_pelota(Pong(semilla=1), 40, 200, -300, 0)
    ev = j.actualizar(0.05)
    assert EventoPong.GOLPE in ev
    assert j.pelota.vx == pytest.approx(300 * ACELERACION) and j.pelota.vy == pytest.approx(0)


def test_golpe_en_el_borde_sale_en_angulo():
    """Impacto en el borde inferior de la paleta (rel = +1) → sale a +60°: vy/vx = tan 60° ≈ 1.732."""
    j = Pong(semilla=1)
    borde = j.izq.y + j.izq.alto  # 235
    con_pelota(j, 40, borde, -300, 0)
    j.actualizar(0.05)
    assert j.pelota.vy / j.pelota.vx == pytest.approx(math.tan(math.radians(60)), rel=1e-3)


def test_anti_tunel_con_dt_grande():
    """A 900 px/s con dt = 0.1 s la pelota recorrería 90 px de golpe (atravesaría una paleta de 10 px);
    con subpasos de ≤ 4 px igual detecta el golpe."""
    j = con_pelota(Pong(semilla=1, velocidad_max=2000), 80, 200, -900, 0)
    assert EventoPong.GOLPE in j.actualizar(0.1)
    assert j.pelota.vx > 0


def test_punto_y_resaque_hacia_quien_perdio():
    """La pelota sale por la izquierda → punto del jugador derecho y re-saque hacia la izquierda."""
    j = con_pelota(Pong(semilla=1), 5, 10, -300, 0)  # muy arriba: la paleta (165..235) no la alcanza
    ev = j.actualizar(0.1)
    assert EventoPong.PUNTO_DER in ev and j.marcador == [0, 1]
    assert j.pelota.vx < 0 and (j.pelota.x, j.pelota.y) == (320, 200)


def test_fin_de_partida():
    """Al llegar a puntos_para_ganar se termina, hay ganador y actualizar ya no hace nada."""
    j = Pong(semilla=1, puntos_para_ganar=1)
    con_pelota(j, 635, 10, 300, 0)
    j.actualizar(0.1)
    assert j.terminado and j.ganador == 0 and j.actualizar(0.1) == []


def test_paleta_acotada_al_campo():
    """La paleta se mueve a 360 px/s y no sale del campo (y ∈ [0, 400-70])."""
    j = Pong(semilla=1)
    j.actualizar(10, dir_izq=-1)
    assert j.izq.y == 0
    j.actualizar(10, dir_izq=1)
    assert j.izq.y == 330


def test_ia():
    """La IA sube/baja hacia la pelota y se queda quieta dentro de la zona muerta (±10 px)."""
    j = Pong(semilla=1)  # centro de la paleta derecha = 200
    j.pelota.y = 300
    assert ia(j.der, j.pelota) == 1
    j.pelota.y = 205
    assert ia(j.der, j.pelota) == 0
    j.pelota.y = 50
    assert ia(j.der, j.pelota) == -1


def test_partida_ia_contra_ia_termina():
    """Simulación headless: dos IAs a 60 FPS. Debe terminar (alguien llega a 5) en < 20 min simulados
    y la pelota nunca escapa verticalmente del campo."""
    j = Pong(semilla=42)
    for _ in range(60 * 60 * 20):
        j.actualizar(1 / 60, ia(j.izq, j.pelota), ia(j.der, j.pelota))
        assert 0 <= j.pelota.y <= j.alto
        if j.terminado:
            break
    assert j.terminado and max(j.marcador) == 5
