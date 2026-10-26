"""Tests del controlador con el motor falso (sin audio real)."""
from pathlib import Path

from reproductor.audio import MotorFalso
from reproductor.control import Estado, Reproductor
from reproductor.lista import ListaReproduccion

P = [Path(f"{c}.mp3") for c in "abc"]


def nuevo(**kw):
    """Arma un motor falso (con las opciones dadas, p. ej. archivos que fallan) y un
    reproductor con las pistas a, b, c.
    """
    motor = MotorFalso(**kw)
    return motor, Reproductor(motor, ListaReproduccion(P))


def test_play_pausa_reanudar_detener():
    """El mismo botón ▶/⏸ alterna: primero carga+reproduce, después pausa, después reanuda (no
    recarga). En pausa, ``tick`` no debe confundir 'no sonando' con fin de pista. Se
    verifica la secuencia exacta de llamadas al motor.
    """
    m, r = nuevo()
    r.reproducir_pausar()
    assert r.estado is Estado.REPRODUCIENDO and m.cargada.name == "a.mp3"
    r.reproducir_pausar()
    assert r.estado is Estado.PAUSADO
    r.tick()                                          # en pausa no avanza
    assert m.cargada.name == "a.mp3"
    r.reproducir_pausar()
    r.detener()
    assert m.llamadas == ["cargar:a.mp3", "reproducir", "pausar", "reanudar", "detener"]


def test_fin_de_pista_avanza_y_se_detiene_al_final():
    """Simula el fin de cada pista: a → b → c y, sin repetición, al terminar c queda DETENIDO."""
    m, r = nuevo()
    r.reproducir_pausar()
    for esperado in ("b.mp3", "c.mp3"):
        m.terminar_pista(); r.tick()
        assert m.cargada.name == esperado
    m.terminar_pista(); r.tick()
    assert r.estado is Estado.DETENIDO


def test_archivo_roto_se_salta():
    """Si a.mp3 no abre, se registra el error y se pasa a b.mp3 sin cortar la reproducción."""
    m, r = nuevo(fallar_con={"a.mp3"})
    r.reproducir_pausar()
    assert m.cargada.name == "b.mp3" and r.errores and "a.mp3" in r.errores[0]


def test_todos_rotos_no_bucle_infinito():
    """Con repetir-todas y las 3 pistas rotas, el salto de archivos rotos se corta tras una
    vuelta (3 errores) en vez de girar para siempre.
    """
    m, r = nuevo(fallar_con={"a.mp3", "b.mp3", "c.mp3"})
    r.lista.repetir = r.lista.repetir.TODAS
    r.reproducir_pausar()
    assert r.estado is Estado.DETENIDO and len(r.errores) == 3


def test_volumen_limitado_y_elegir():
    """El volumen se acota a [0, 1] (1.7 → 1.0, -1 → 0.0) y elegir(2) reproduce c.mp3
    directamente.
    """
    m, r = nuevo()
    assert r.fijar_volumen(1.7) == 1.0 and m.volumen == 1.0
    assert r.fijar_volumen(-1) == 0.0
    r.elegir(2)
    assert m.cargada.name == "c.mp3" and r.estado is Estado.REPRODUCIENDO
