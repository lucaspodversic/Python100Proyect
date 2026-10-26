"""Test de humo de la GUI (se omite si no hay pantalla)."""
import importlib


def test_gui_importable_sin_pantalla():
    """El módulo de GUI se puede importar sin pantalla: Tk solo se instancia en main()."""
    # Importar no debe crear ventanas ni requerir DISPLAY.
    assert hasattr(importlib.import_module("calc.gui"), "main")


def test_flujo_basico(raiz):
    """Recorrido por los botones como lo haría un usuario. 2+3×4 respeta precedencia → 14 (no
    20) y queda en el historial; 1÷0 muestra 'Error…' en la pantalla en vez de lanzar;
    alternar_modo cambia el rótulo a DEG.
    """
    from calc.gui import AppCalculadora

    app = AppCalculadora(raiz)
    for tecla in ("2", "+", "3", "×", "4", "<igual>"):
        app.pulsar(tecla)
    assert app.entrada.get() == "14"
    assert app.lista.get(0) == "2+3×4 = 14"
    app.pulsar("<borrar>")
    for tecla in ("1", "÷", "0", "<igual>"):
        app.pulsar(tecla)
    assert app.entrada.get().startswith("Error")
    app.alternar_modo()
    assert app.estado.get() == "DEG"
