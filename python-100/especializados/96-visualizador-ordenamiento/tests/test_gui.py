"""Tests de la GUI. Se saltean sin DISPLAY (ver conftest)."""
def test_importable_sin_display():
    """Importar el módulo no debe crear ventanas, así funciona incluso sin servidor X."""
    import ordenvis.gui  # noqa: F401  (no crea ventanas al importar)


def test_humo_gui(raiz):
    """Con 20 elementos se dibujan 20 barras. Al avanzar se cuentan pasos; cambiar de algoritmo
    reinicia los contadores. Al terminar, la info lo dice y Play desde terminado
    reinicia y programa un after().
    """
    from ordenvis.gui import AppOrden
    app = AppOrden(raiz, n=20, semilla=1)
    app.pack()
    raiz.update()
    assert len(app.canvas.find_all()) == 20
    app.paso(5)
    assert app.rep.stats.pasos > 0
    app.var_alg.set("Heapsort")          # cambiar algoritmo reinicia con el mismo arreglo
    assert app.rep.algoritmo == "Heapsort" and app.rep.stats.pasos == 0
    app.rep.completar(); app.dibujar()
    assert "terminado" in app.var_info.get()
    app.alternar()                        # play desde terminado → reinicia y programa after()
    assert app._job is not None
    app.pausar()
    assert app._job is None
