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


@pytest.fixture()
def carpeta(tmp_path):
    """Carpeta con imágenes generadas en el test (nada se versiona)."""
    from PIL import Image

    Image.new("RGB", (40, 20), "red").save(tmp_path / "img2.png")
    Image.new("RGBA", (10, 10), (0, 0, 255, 128)).save(tmp_path / "img10.png")
    Image.new("RGB", (8, 8), "green").save(tmp_path / "foto.jpg")
    (tmp_path / "roto.png").write_bytes(b"no soy una imagen")
    (tmp_path / "notas.txt").write_text("x")
    return tmp_path
