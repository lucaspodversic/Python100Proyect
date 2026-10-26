"""Tests con SQLite en memoria / tmp_path y fecha fija."""
from datetime import date

import pytest

from tareas import Prioridad, Repositorio, Tarea, parsear_fecha
from tareas.cli import ejecutar

# Fecha fija: los tests no dependen del día en que se corren.
HOY = date(2026, 10, 26)  # lunes


# "lunes" siendo lunes → el de la semana siguiente (nunca hoy).
@pytest.mark.parametrize("txt,esp", [("hoy", HOY), ("mañana", date(2026, 10, 27)), ("+10", date(2026, 11, 5)),
                                     ("viernes", date(2026, 10, 30)), ("lunes", date(2026, 11, 2)),
                                     ("2026-12-24", date(2026, 12, 24))])
def test_fechas(txt, esp):
    assert parsear_fecha(txt, HOY) == esp


# Textos irreconocibles → ValueError; alias de una letra.
def test_fecha_y_prioridad_invalidas():
    with pytest.raises(ValueError):
        parsear_fecha("algún día", HOY)
    with pytest.raises(ValueError):
        Prioridad.desde_texto("urgentísima")
    assert Prioridad.desde_texto("a") is Prioridad.ALTA


# Orden: misma fecha → la de mayor prioridad primero; sin fecha al final; las hechas, ocultas o al final.
def test_crud_y_orden():
    r = Repositorio()
    a = r.agregar(Tarea("sin fecha", Prioridad.ALTA))
    b = r.agregar(Tarea("pronto baja", Prioridad.BAJA, date(2026, 10, 27), {"casa"}))
    c = r.agregar(Tarea("pronto alta", Prioridad.ALTA, date(2026, 10, 27)))
    assert [t.id for t in r.listar()] == [c.id, b.id, a.id]
    c.hecha = True; r.actualizar(c)
    assert [t.id for t in r.listar()] == [b.id, a.id]
    assert r.listar(incluir_hechas=True)[-1].id == c.id
    assert [t.id for t in r.listar(etiqueta="casa")] == [b.id]
    assert [t.id for t in r.listar(prioridad_min=Prioridad.MEDIA)] == [a.id]
    assert r.limpiar_hechas() == 1
    r.borrar(a.id)
    with pytest.raises(KeyError):
        r.obtener(a.id)


# Vencida, del día y hecha.
def test_estado():
    assert Tarea("x", vence=date(2026, 10, 1)).estado(HOY) == "VENCIDA"
    assert Tarea("x", vence=HOY).estado(HOY) == "hoy"
    assert Tarea("x", hecha=True).estado(HOY) == "hecha"


# Flujo completo con base temporal: agregar, listar, filtrar, editar, completar y errores.
def test_cli_flujo(tmp_path, capsys):
    db = tmp_path / "t.db"
    run = lambda *a: ejecutar(list(a), hoy=HOY, db=db)
    assert run("agregar", "Pagar luz", "-p", "alta", "-v", "viernes", "-e", "casa") == 0
    assert run("agregar", "Leer") == 0
    capsys.readouterr()
    assert run("listar") == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("  1 [ ] !!! 2026-10-30") and "#casa" in out[0]
    # Sólo "Pagar luz" vence dentro de 7 días ("Leer" no tiene fecha).
    assert run("listar", "--hasta", "+7") == 0
    assert len(capsys.readouterr().out.splitlines()) == 1
    assert run("editar", "2", "-v", "hoy", "--titulo", "Leer libro") == 0
    assert run("hecha", "1") == 0
    capsys.readouterr()
    run("listar")
    assert "Leer libro" in capsys.readouterr().out
    # Id inexistente y fecha inválida → exit 1.
    assert run("borrar", "99") == 1
    assert run("agregar", "x", "-v", "nunca") == 1
