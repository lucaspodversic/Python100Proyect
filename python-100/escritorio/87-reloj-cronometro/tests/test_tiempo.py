"""Tests de la lógica de tiempo con relojes falsos (sin esperas reales)."""
from datetime import datetime, time

import pytest

from reloj.tiempo import Alarma, Cronometro, Temporizador, formatear, parsear_duracion


class Reloj:
    """Reloj manual (arranca en 1000 para no confundir 'cero' con 'sin iniciar')."""
    def __init__(self):
        """Tiempo inicial arbitrario."""
        self.t = 1000.0

    def __call__(self):
        """Tiempo actual simulado."""
        return self.t


@pytest.mark.parametrize("seg, cs, esperado", [
    # 3725.5 s = 1 h 2 min 5.5 s.
    (0, False, "00:00:00"), (3725.5, True, "01:02:05.50"),
    # 59.999 redondea a centésimas → 60.00 → se arrastra al minuto (no "00:00:60.00").
    (59.999, True, "00:01:00.00"),
    # Negativos con signo adelante (temporizador vencido).
    (-5, False, "-00:00:05"),
])
def test_formatear(seg, cs, esperado):
    """Formato HH:MM:SS con centésimas opcionales."""
    assert formatear(seg, cs) == esperado


# Segundos solos, MM:SS, H:MM:SS (3600+120+3 = 3723) y unidades (1h 30m = 5400 s).
@pytest.mark.parametrize("texto, seg", [("90", 90), ("05:00", 300), ("1:02:03", 3723), ("1h 30m", 5400), ("45s", 45)])
def test_parsear_duracion(texto, seg):
    """Formatos aceptados para el temporizador."""
    assert parsear_duracion(texto) == seg


@pytest.mark.parametrize("texto", ["", "abc", "0", "1:75", "200h", "h"])
def test_parsear_duracion_invalida(texto):
    """Vacío, texto, duración cero, minutos fuera de rango (1:75), duraciones absurdas (200 h)
    y unidades sin número se rechazan.
    """
    with pytest.raises(ValueError):
        parsear_duracion(texto)


def test_cronometro_pausa_y_vueltas():
    """Vuelta 1 = 10 s. Luego 5 s más y pausa: los 100 s en pausa no cuentan → 15. Al seguir 7
    s, la vuelta 2 mide desde la vuelta 1: 5 + 7 = 12. Vuelta 3 = 3 s. Mejor = índice 2
    (3 s), peor = índice 1 (12 s). En pausa no se puede marcar vuelta.
    """
    r = Reloj()
    c = Cronometro(r)
    c.iniciar(); r.t += 10
    assert c.vuelta() == 10
    r.t += 5; c.pausar(); r.t += 100              # en pausa no cuenta
    assert c.transcurrido() == 15
    c.iniciar(); r.t += 7
    assert c.vuelta() == 12 and c.vueltas == [10, 12]
    r.t += 3
    c.vuelta()
    assert c.mejor_y_peor() == (2, 1)
    c.pausar()
    with pytest.raises(RuntimeError):
        c.vuelta()
    c.reiniciar()
    assert c.transcurrido() == 0 and c.vueltas == []


def test_temporizador_avisa_una_vez():
    """60 s: corre 20 y pausa (los 500 en pausa no cuentan) → faltan 40. Tras 39.5 más,
    progreso = 59.5/60. Al cumplirse, ``comprobar`` devuelve True una sola vez (no
    repite el aviso en cada tick). Reiniciar con otra duración y validar que 0 s no es
    válido.
    """
    r = Reloj()
    t = Temporizador(60, r)
    t.iniciar(); r.t += 20; t.pausar(); r.t += 500
    assert t.restante() == 40 and not t.comprobar()
    t.iniciar(); r.t += 39.5
    assert t.progreso() == pytest.approx(59.5 / 60)
    r.t += 1
    assert t.terminado and t.comprobar() and not t.comprobar()
    t.reiniciar(10)
    assert t.restante() == 10
    with pytest.raises(ValueError):
        Temporizador(0)


def test_alarma_suena_una_vez_por_dia_y_snooze():
    """2026-01-05 es lunes. Suena dentro del primer minuto (07:00:30) y no vuelve a sonar ese
    día. Pospuesta 5 min desde 07:01 → suena a las 07:06, no antes. Después de las 8 la
    próxima es mañana a las 7. Si la app estuvo cerrada y pasaron más de 60 s, la alarma
    se considera perdida (no suena tarde).
    """
    a = Alarma.desde_texto("07:00", "Trabajo")
    assert not a.debe_sonar(datetime(2026, 1, 5, 6, 59, 59))
    assert a.debe_sonar(datetime(2026, 1, 5, 7, 0, 30))
    assert not a.debe_sonar(datetime(2026, 1, 5, 7, 0, 40))   # ya sonó hoy
    hasta = a.posponer(datetime(2026, 1, 5, 7, 1), minutos=5)
    assert a.proxima(datetime(2026, 1, 5, 7, 2)) == hasta
    assert not a.debe_sonar(datetime(2026, 1, 5, 7, 5)) and a.debe_sonar(hasta)
    assert a.proxima(datetime(2026, 1, 5, 8)) == datetime(2026, 1, 6, 7)
    assert not a.debe_sonar(datetime(2026, 1, 6, 7, 5))      # más de 60 s tarde: se perdió


def test_alarma_dias_y_desactivada():
    """Alarma lun/mié: un martes no suena y la próxima es el miércoles. Desactivada no tiene
    próxima ni suena.
    """
    a = Alarma(time(9, 0), "Gym", frozenset({0, 2}))           # lun y mié
    # 2026-01-06 es martes: la próxima es el miércoles 7.
    assert a.proxima(datetime(2026, 1, 6, 10)) == datetime(2026, 1, 7, 9)
    assert not a.debe_sonar(datetime(2026, 1, 6, 9, 0, 1))
    assert a.descripcion() == "09:00 Gym (lun, mié)"
    a.activa = False
    assert a.proxima(datetime(2026, 1, 6)) is None and not a.debe_sonar(datetime(2026, 1, 7, 9))


@pytest.mark.parametrize("texto", ["24:00", "7", "07:60", "aa:bb"])
def test_alarma_hora_invalida(texto):
    """Horas fuera de rango o sin formato HH:MM."""
    with pytest.raises(ValueError):
        Alarma.desde_texto(texto)
