"""Tests de la lógica de Snake (sin pygame).

Tablero por defecto 20x15: la serpiente arranca en (10,7),(9,7),(8,7) mirando a la derecha.
"""
import pytest

from juegos.snake import Dir, Evento, Snake


def test_estado_inicial():
    """Cabeza en el centro (20//2, 15//2) = (10, 7), 3 celdas, comida en una celda libre."""
    j = Snake(semilla=1)
    assert list(j.cuerpo) == [(10, 7), (9, 7), (8, 7)]
    assert j.comida not in j.cuerpo and j.vivo


def test_avanza_y_conserva_largo():
    j = Snake(semilla=1)
    j.comida = (0, 0)  # lejos, para que no interfiera
    j.tick()
    assert list(j.cuerpo) == [(11, 7), (10, 7), (9, 7)]


def test_no_gira_180_y_encola_giros():
    """Yendo a la derecha, "izquierda" se ignora. Arriba+izquierda en el mismo tick se aplican en
    dos ticks seguidos (cola de giros), sin perder el primero."""
    j = Snake(semilla=1)
    j.comida = (0, 0)
    j.girar(Dir.IZQUIERDA)
    j.tick()
    assert j.cabeza == (11, 7)
    j.girar(Dir.ARRIBA); j.girar(Dir.IZQUIERDA)
    j.tick(); assert j.cabeza == (11, 6)
    j.tick(); assert j.cabeza == (10, 6)


def test_comer_crece_y_suma():
    """Al comer suma 10 puntos; el largo pasa de 3 a 4 en el tick SIGUIENTE (la cola no se mueve)."""
    j = Snake(semilla=1)
    j.comida = (11, 7)
    assert j.tick() is Evento.COMIO and j.puntos == 10 and len(j.cuerpo) == 3
    j.comida = (0, 0)
    j.tick()
    assert len(j.cuerpo) == 4 and j.comida != (11, 7)


def test_choque_con_pared():
    """Desde x=10, la pared derecha (x=20) se alcanza en el tick 10."""
    j = Snake(semilla=1)
    j.comida = (0, 0)
    eventos = [j.tick() for _ in range(10)]
    assert eventos[-1] is Evento.CHOCO and not j.vivo
    assert j.tick() is Evento.NADA  # muerto: no se mueve más


def test_sin_paredes_da_la_vuelta():
    j = Snake(semilla=1, paredes=False)
    j.comida = (0, 0)
    for _ in range(10):
        j.tick()
    assert j.cabeza == (0, 7) and j.vivo  # 10 + 10 = 20 → 20 % 20 = 0


def test_choque_consigo_misma():
    """Con largo 5, girar abajo-izquierda-arriba hace que la cabeza entre en el cuerpo."""
    j = Snake(semilla=1)
    j.cuerpo.extend([(7, 7), (6, 7)])
    j.comida = (0, 0)
    j.girar(Dir.ABAJO); j.tick()
    j.girar(Dir.IZQUIERDA); j.tick()
    j.girar(Dir.ARRIBA)
    assert j.tick() is Evento.CHOCO


def test_perseguir_la_cola_no_es_choque():
    """Un cuadrado de 4 celdas: la cabeza entra donde estaba la cola, que se libera en el mismo tick."""
    j = Snake(ancho=5, alto=5, semilla=1)
    j.cuerpo.clear(); j.cuerpo.extend([(1, 1), (1, 2), (2, 2), (2, 1)])  # cabeza (1,1), cola (2,1)
    j.direccion = Dir.ARRIBA
    j.comida = (4, 4)
    j.girar(Dir.DERECHA)
    assert j.tick() is Evento.NADA and j.vivo and j.cabeza == (2, 1)


def test_ganar_llenando_el_tablero():
    """Tablero 5x3 = 15 celdas: si el largo + crecimiento pendiente llega a 15, se gana."""
    j = Snake(ancho=5, alto=3, semilla=1)
    j.cuerpo.clear()
    # Serpiente en zigzag que ocupa 14 celdas; la que falta es (4, 0), justo delante de la cabeza.
    fila0 = [(3, 0), (2, 0), (1, 0), (0, 0)]
    fila1 = [(0, 1), (1, 1), (2, 1), (3, 1), (4, 1)]
    fila2 = [(4, 2), (3, 2), (2, 2), (1, 2), (0, 2)]
    j.cuerpo.extend(fila0 + fila1 + fila2)
    j.direccion = Dir.DERECHA
    j.comida = (4, 0)
    assert j.tick() is Evento.GANO and j.gano


def test_comida_determinista_y_validaciones():
    """Misma semilla → misma comida. Tableros menores a 5x3 se rechazan."""
    assert Snake(semilla=7).comida == Snake(semilla=7).comida
    with pytest.raises(ValueError):
        Snake(ancho=3)


def test_velocidad():
    """8 ticks/s de base + 0.5 por comida (10 puntos), tope 20 (alcanzado con 24 comidas)."""
    j = Snake()
    assert j.velocidad() == 8
    j.puntos = 40
    assert j.velocidad() == 10
    j.puntos = 1000
    assert j.velocidad() == 20
