"""Tests de la GUI con el capturador falso: no capturan la pantalla real."""
from PIL import Image

from captura.capturador import CapturadorFalso, Region


def test_gui_importable():
    """Importar la GUI no crea ventanas."""
    import captura.gui as g
    assert callable(g.main)


def test_gui_captura(raiz, tmp_path):
    """Captura de 40×30 como JPG con nombre puntual: archivo con ese nombre y tamaño; el nombre
    se limpia tras usarlo.
    """
    from captura.gui import AppCaptura
    app = AppCaptura(raiz, CapturadorFalso(), carpeta=tmp_path)
    app.var_nombre.set("prueba")
    app.var_formato.set("jpg")
    ruta = app.capturar_ahora(Region(0, 0, 40, 30))
    assert ruta == tmp_path / "prueba.jpg" and Image.open(ruta).size == (40, 30)
    assert app.var_nombre.get() == "" and "Guardada" in app.estado.get()


def test_selector_region(raiz):
    """Arrastrar de (200,150) a (50,40), o sea hacia arriba y a la izquierda, da la región
    normalizada x=50, y=40, 150×110. Cancelar entrega None.
    """
    from captura.gui import SelectorRegion
    elegidas = []
    sel = SelectorRegion(raiz, elegidas.append)
    sel.empezar(200, 150, 200, 150)
    sel.mover(50, 40)
    sel.terminar(50, 40)
    assert elegidas == [Region(50, 40, 150, 110)]
    sel2 = SelectorRegion(raiz, elegidas.append)
    sel2.cancelar()
    assert elegidas[-1] is None
