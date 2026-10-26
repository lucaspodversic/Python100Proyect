"""Test de humo de la GUI (se omite sin pantalla)."""
from editor.nucleo import Recientes


def test_gui_importable():
    """Importar la GUI no crea ventanas ni requiere pantalla."""
    import editor.gui as g

    assert callable(g.main)


def test_gui_abrir_buscar_reemplazar_guardar(raiz, tmp_path):
    """Flujo completo: abrir pone el nombre en el título; 'uno' aparece 2 veces y cada hallazgo
    es un rango (inicio, fin) → 4 marcas; reemplazar marca el documento como modificado
    ('*' en el título); guardar escribe el resultado en disco.
    """
    from editor.gui import AppEditor

    archivo = tmp_path / "nota.txt"
    archivo.write_text("uno dos uno\n")
    app = AppEditor(raiz, Recientes(tmp_path / "rec.json"))
    assert app.abrir(archivo)
    assert raiz.title() == "nota.txt — Editor"
    assert app.resaltar("uno") == 2
    assert len(app.texto.tag_ranges("hallazgo")) == 4
    assert app.reemplazar_todo("uno", "1") == 2
    assert app.doc.modificado and raiz.title().startswith("*")
    assert app.guardar()
    assert archivo.read_text() == "1 dos 1\n"
    app.texto.event_generate("<<Undo>>")
    assert app._contenido() == "uno dos uno\n"
