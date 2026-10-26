"""Test de humo de la GUI con el motor falso (se omite sin pantalla)."""
from pathlib import Path

from reproductor.audio import MotorFalso


def test_gui_importable():
    """Importar la GUI no requiere pantalla ni pygame."""
    import reproductor.gui as g

    assert callable(g.main)


def test_gui_flujo(raiz):
    """Con un motor falso: cargar dos pistas llena la lista; play muestra '▶ uno' y selecciona
    la fila 0; siguiente pasa a 'dos'; el botón de repetir rota de 'no' a 'todas'.
    """
    from reproductor.gui import AppReproductor

    motor = MotorFalso()
    app = AppReproductor(raiz, motor)
    app.cargar([Path("uno.mp3"), Path("dos.mp3")])
    assert app.lista.size() == 2
    app._accion(app.rep.reproducir_pausar)
    assert app.titulo.get() == "▶ uno" and app.lista.curselection() == (0,)
    app._accion(app.rep.siguiente)
    assert app.titulo.get() == "▶ dos"
    app._repetir()
    assert app.btn_repetir.cget("text") == "Repetir: todas"
