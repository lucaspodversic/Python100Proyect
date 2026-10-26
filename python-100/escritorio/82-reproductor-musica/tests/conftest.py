"""Fixtures compartidas de los tests.

``raiz`` crea una ventana Tk real solo si hay un servidor gráfico disponible
(DISPLAY / Xvfb). Si no lo hay, los tests de humo de la GUI se **omiten**
(skip) en lugar de fallar: la lógica se prueba igual en sus propios tests.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture()
def raiz():
    """Ventana Tk raíz oculta para los tests de GUI. Se saltea si no hay tkinter, si no hay
    DISPLAY o si el servidor X no responde. Al final la destruye, tolerando que la app
    ya la haya cerrado.
    """
    tk = pytest.importorskip("tkinter")
    if os.name != "nt" and not os.environ.get("DISPLAY"):
        pytest.skip("sin DISPLAY: se omite el test de humo de la GUI")
    try:
        r = tk.Tk()
    except tk.TclError as e:  # DISPLAY definido pero inaccesible
        pytest.skip(f"Tk no disponible: {e}")
    r.withdraw()  # no mostrar la ventana durante los tests
    yield r
    try:
        r.destroy()
    except tk.TclError:  # la propia app ya cerró la ventana (p. ej. botón "salir")
        pass
