"""Tests del almacén y del autoguardado (sin GUI)."""
import json

import pytest

from notas.almacen import Almacen, Nota
from notas.autoguardado import Autoguardado


class Reloj:
    """Reloj falso controlable."""

    def __init__(self):
        """Empieza en t=0."""
        self.t = 0.0

    def __call__(self):
        """Devuelve el tiempo actual simulado."""
        return self.t


def test_debounce():
    """Espera 1.5 s. Cambio en t=0 y otro en t=1: el debounce cuenta desde el último (1.0), así
    que en t=2.4 faltan 0.1 s y en t=2.5 ya hay que guardar. Tras guardar no queda nada
    pendiente.
    """
    r = Reloj()
    a = Autoguardado(espera=1.5, maximo=10, reloj=r)
    assert not a.debe_guardar()
    a.marcar_cambio(); r.t = 1.0
    assert not a.debe_guardar()
    a.marcar_cambio(); r.t = 2.4                     # sigue escribiendo: se pospone
    assert not a.debe_guardar()
    r.t = 2.5
    assert a.debe_guardar()
    a.guardado()
    assert not a.pendiente and not a.debe_guardar()


def test_plazo_maximo_escribiendo_sin_parar():
    """Un cambio por segundo nunca deja 1.5 s de pausa, pero en t=10 se cumplen los 10 s desde
    el primer cambio y se guarda igual.
    """
    r = Reloj()
    a = Autoguardado(espera=1.5, maximo=10, reloj=r)
    while r.t < 10:
        a.marcar_cambio()
        assert not a.debe_guardar()
        r.t += 1.0
    a.marcar_cambio()
    assert a.debe_guardar()


def test_parametros_invalidos():
    """espera > maximo es una configuración sin sentido."""
    with pytest.raises(ValueError):
        Autoguardado(espera=5, maximo=1)


def test_titulo():
    """El título es la primera línea no vacía sin '#' de Markdown; texto en blanco → '(vacía)';
    más de 60 caracteres se corta con '…'.
    """
    assert Nota("x", "\n\n# Compras  \nleche").titulo == "Compras"
    assert Nota("x", "   ").titulo == "(vacía)"
    assert Nota("x", "a" * 80).titulo.endswith("…")


@pytest.fixture()
def almacen(tmp_path):
    """Almacén en carpeta temporal con un reloj que avanza un segundo por llamada: cada
    crear/guardar tiene fecha distinta y el orden es predecible.
    """
    marcas = iter(f"2026-01-01T00:00:{s:02d}+00:00" for s in range(60))
    return Almacen(tmp_path, reloj=lambda: next(marcas))


def test_crud_orden_y_filtro(almacen):
    """Orden por modificación descendente: b es más nueva → [Ideas, Compras]; al editar a pasa
    adelante. Fijar b (sin tocar fecha) la pone primera igual. El filtro no distingue
    mayúsculas ('PAN' encuentra 'pan').
    """
    a = almacen.crear("Compras\nleche")
    b = almacen.crear("Ideas")
    assert [n.titulo for n in almacen.listar()] == ["Ideas", "Compras"]
    a.texto += "\npan"
    almacen.guardar(a)
    assert [n.titulo for n in almacen.listar()] == ["Compras", "Ideas"]
    b.fijada = True
    almacen.guardar(b, tocar=False)
    assert [n.titulo for n in almacen.listar()] == ["Ideas", "Compras"]
    assert [n.titulo for n in almacen.listar("PAN")] == ["Compras"]
    assert almacen.leer(a.id).texto.endswith("pan")


def test_papelera(almacen):
    """Borrar mueve a la papelera (desaparece del listado), restaurar la devuelve intacta y
    vaciar la papelera la elimina (devuelve 1).
    """
    n = almacen.crear("borrame")
    almacen.borrar(n.id)
    assert almacen.listar() == [] and almacen.en_papelera() == [n.id]
    assert almacen.restaurar(n.id).texto == "borrame"
    almacen.borrar(n.id)
    assert almacen.vaciar_papelera() == 1 and almacen.en_papelera() == []


def test_corruptas_se_reportan_y_ids_validados(almacen, tmp_path):
    """Un JSON roto no impide listar las demás y queda registrado en ``corruptas``. Un id con
    '../' se rechaza (evita leer archivos fuera de la carpeta).
    """
    almacen.crear("ok")
    (tmp_path / ("f" * 32 + ".json")).write_text("{roto")
    assert len(almacen.listar()) == 1 and almacen.corruptas == ["f" * 32 + ".json"]
    with pytest.raises(ValueError):
        almacen.leer("../../etc/passwd")


def test_guardado_atomico_sin_temporales(almacen, tmp_path, monkeypatch):
    """Si falla el renombrado final, el archivo sigue con la versión anterior (v1) y no quedan
    temporales '.tmp-*'.
    """
    n = almacen.crear("v1")
    n.texto = "v2"
    monkeypatch.setattr("notas.almacen.os.replace", lambda *a: (_ for _ in ()).throw(OSError("lleno")))
    with pytest.raises(OSError):
        almacen.guardar(n)
    assert json.loads((tmp_path / f"{n.id}.json").read_text())["texto"] == "v1"
    assert not list(tmp_path.glob(".tmp-*"))
