"""Test de humo de la GUI con reloj falso (se omite sin pantalla)."""
from notas.almacen import Almacen
from notas.autoguardado import Autoguardado


def test_gui_importable():
    """Importar la GUI no crea ventanas ni requiere pantalla."""
    import notas.gui as g

    assert callable(g.main)


def test_gui_autoguarda(raiz, tmp_path):
    """Reloj falso en t=0 y espera de 1 s. Escribir marca el cambio como pendiente; con el
    reloj en t=2 (>1 s sin tocar) el sondeo guarda: la nota aparece en disco y en la
    lista con su título.
    """
    from notas.gui import AppNotas

    t = [0.0]
    almacen = Almacen(tmp_path)
    app = AppNotas(raiz, almacen, Autoguardado(espera=1, maximo=5, reloj=lambda: t[0]))
    app.nueva()
    app.texto.insert("end", "Lista del súper")
    raiz.update()                                    # procesa <<Modified>>
    assert app.auto.pendiente
    t[0] = 2.0
    app._sondear()                                   # el sondeo decide guardar
    assert almacen.listar()[0].texto == "Lista del súper"
    assert app.lista.get(0) == "Lista del súper"
    app.texto.insert("end", "!")
    raiz.update()
    app.cerrar()                                     # al cerrar guarda lo pendiente
    assert almacen.listar()[0].texto == "Lista del súper!"
