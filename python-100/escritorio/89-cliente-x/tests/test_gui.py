"""Tests de la GUI con el servicio falso y ejecutor sincrónico (sin hilos ni red)."""
from clientex.api import Post, ServicioFalso
from clientex.control import ejecutor_sincrono


def test_gui_importable():
    """Importar la GUI no crea ventanas."""
    import clientex.gui as g
    assert callable(g.main)


def test_gui_flujo(raiz):
    """Conectar muestra 1 post; 'nuevo post' tiene 10 caracteres → quedan 270; al publicar
    aparece arriba y el redactor se vacía.
    """
    from clientex.gui import AppX
    s = ServicioFalso(posts=[Post("1", "hola", "demo")])
    app = AppX(raiz, s, ejecutor=ejecutor_sincrono)
    app.ctrl.conectar()
    assert app.lista.size() == 1
    app.redactor.insert("1.0", "nuevo post")
    app._contar()
    assert app.contador.get() == str(280 - 10)
    app.publicar()
    assert app.lista.get(0).startswith("@demo: nuevo post")
    assert app._texto() == ""
