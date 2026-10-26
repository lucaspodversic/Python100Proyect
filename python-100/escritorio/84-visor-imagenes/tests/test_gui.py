"""Test de humo de la GUI (se omite sin pantalla)."""


def test_gui_importable():
    """Importar la GUI no crea ventanas ni requiere pantalla."""
    import visor.gui as g

    assert callable(g.main)


def test_gui_navega_y_omite_rotas(raiz, carpeta):
    """Orden natural: foto.jpg, img2, img10, roto. Desde img10 (10×10), avanzar llega a
    roto.png, que no abre: se omite, se quita de la galería y se sigue (con vuelta)
    hasta foto.jpg; quedan 3. 1:1 y un acercar → 1 × 1.25 = 125 %, visible en la barra
    de estado.
    """
    from visor.gui import AppVisor

    raiz.geometry("400x300")
    app = AppVisor(raiz)
    app.pack(fill="both", expand=True)
    app.cargar(carpeta / "img10.png")
    assert app.imagen.size == (10, 10)
    app.mover(1)                     # roto.png se omite y se quita
    assert app.galeria.actual.name == "foto.jpg" and len(app.galeria.rutas) == 3
    app.real(); app.acercar()
    assert app.vista.zoom == 1.25 and "zoom 125%" in app.estado.get()
    app.rotar(90)
    assert app.vista.rotacion == 90
