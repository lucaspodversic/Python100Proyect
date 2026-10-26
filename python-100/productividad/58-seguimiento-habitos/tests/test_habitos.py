"""Tests con fechas fijas."""
from datetime import date, timedelta

import pytest

from habitos import Almacen, Habito, estadisticas
from habitos.cli import ejecutar, parsear_dias
from habitos.modelo import calendario

# Fecha fija de referencia (un lunes) para todos los tests.
LUN = date(2026, 10, 5)  # lunes


def dias(inicio, *offs):
    """Conjunto de fechas a `offs` días de `inicio`."""
    return {inicio + timedelta(o) for o in offs}


# Hechos lun-mar-mié, falla jue, hechos vie-sáb: actual 2, mejor 3.
def test_rachas_diarias():
    h = Habito("leer", LUN, hechos=dias(LUN, 0, 1, 2, 4, 5))
    e = estadisticas(h, LUN + timedelta(5))
    assert (e.racha_actual, e.mejor_racha, e.total) == (2, 3, 5)


# Hoy sin marcar no corta la racha; si el día que faltó fue ayer, sí.
def test_hoy_pendiente_no_rompe_racha():
    h = Habito("leer", LUN, hechos=dias(LUN, 0, 1))
    assert estadisticas(h, LUN + timedelta(2)).racha_actual == 2
    assert estadisticas(h, LUN + timedelta(3)).racha_actual == 0  # ayer se cortó


# Hábito lun/mié/vie: los días no programados no cortan la racha.
def test_dias_programados():
    h = Habito("gym", LUN, frozenset({0, 2, 4}), dias(LUN, 0, 2, 4, 7))  # lun mié vie lun
    e = estadisticas(h, LUN + timedelta(8))  # martes siguiente (no toca)
    assert e.racha_actual == 4 and e.cumplimiento == 1.0


# 3 de 10 días cumplidos = 30 %; marcar antes de la creación es error.
def test_cumplimiento_ventana():
    h = Habito("agua", LUN, hechos=dias(LUN, 0, 1, 2))
    assert estadisticas(h, LUN + timedelta(9), ventana=10).cumplimiento == pytest.approx(0.3)
    with pytest.raises(ValueError):
        h.marcar(LUN - timedelta(1))


# Lunes hecho (█), martes = hoy sin hacer (·), miércoles futuro (espacio).
def test_calendario():
    h = Habito("x", LUN, hechos=dias(LUN, 0))
    cal = calendario(h, LUN + timedelta(1), semanas=1).splitlines()
    assert cal[0] == "L █" and cal[1] == "M ·" and cal[2] == "X  "


# Guardar y volver a cargar da lo mismo y no queda ningún .tmp suelto.
def test_almacen_ida_y_vuelta(tmp_path):
    alm = Almacen(tmp_path / "h.json")
    hs = {"gym": Habito("gym", LUN, frozenset({0, 4}), dias(LUN, 0))}
    alm.guardar(hs)
    assert alm.cargar() == hs and list(tmp_path.glob("*.tmp")) == []


# "lmv" = lunes, martes y viernes (miércoles es "x").
def test_parsear_dias():
    assert parsear_dias("lmv") == {0, 1, 4} and len(parsear_dias("todos")) == 7
    with pytest.raises(ValueError):
        parsear_dias("q")


# Flujo: crear, duplicado (error), marcar dos días, ver, deshacer, hábito inexistente y borrar.
def test_cli(tmp_path, capsys):
    f = tmp_path / "h.json"
    run = lambda *a, hoy=LUN: ejecutar(list(a), hoy=hoy, archivo=f)
    assert run("nuevo", "leer") == 0
    assert run("nuevo", "leer") == 1
    assert run("hecho", "leer") == 0
    assert run("hecho", "leer", hoy=LUN + timedelta(1)) == 0
    capsys.readouterr()
    assert run("ver", hoy=LUN + timedelta(1)) == 0
    assert "racha 2 (mejor 2)" in capsys.readouterr().out
    assert run("deshacer", "leer", "--fecha", "2026-10-06") == 0
    assert run("hecho", "correr") == 1
    assert run("borrar", "leer") == 0
    capsys.readouterr(); run("ver")
    assert "Todavía no hay" in capsys.readouterr().out
