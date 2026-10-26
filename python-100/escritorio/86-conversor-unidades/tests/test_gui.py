"""Test de humo de la GUI (se omite sin pantalla)."""


def test_gui_importable():
    """Importar la GUI no crea ventanas ni requiere pantalla."""
    import conversor.gui as g

    assert callable(g.main)


def test_gui_en_vivo(raiz):
    """37 °C = 37·9/5 + 32 = 98.6 °F, calculado al escribir. La tabla muestra las 4 unidades de
    temperatura. Intercambiar pasa el resultado a °C y un valor no numérico muestra una
    advertencia ⚠ en vez de lanzar.
    """
    from conversor.gui import AppConversor

    app = AppConversor(raiz)
    app.magnitud.set("temperatura")
    app._cambiar_magnitud()
    app.de.set("°C"); app.a.set("°F"); app.valor.set("37")
    assert app.resultado.get() == "= 98.6 °F"
    assert len(app.tabla.get_children()) == 4
    app.intercambiar()
    assert app.resultado.get().endswith("°C")
    app.valor.set("hola")
    assert app.resultado.get().startswith("⚠")
