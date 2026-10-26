"""Tests unitarios de utilidades de contenido."""
from app import contenido


def test_slug():
    """Sin tildes ni signos y en minúsculas; si no queda nada, 'articulo'. Con 'a' y 'a-2'
    usados, el siguiente libre es 'a-3'.
    """
    assert contenido.slugificar("¡Hola, Año Nuevo!") == "hola-ano-nuevo"
    assert contenido.slugificar("???") == "articulo"
    usados = {"a", "a-2"}
    assert contenido.slug_unico("a", usados.__contains__) == "a-3"


def test_render_seguro():
    """El Markdown básico se convierte, pero el HTML crudo se escapa (no se ejecuta <script>) y
    los enlaces javascript: se descartan; solo se permiten esquemas seguros como https.
    """
    html = contenido.renderizar("# Título\n\nHola **mundo** <script>alert(1)</script>\n\n"
                                "[ok](https://x.com) [malo](javascript:alert(1))")
    assert "<h1>Título</h1>" in html and "<strong>mundo</strong>" in html
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert '<a href="https://x.com"' in html and 'href="javascript' not in html


def test_detectar_imagen():
    """El tipo se decide por los primeros bytes (números mágicos) y no por la extensión: un PHP
    no es una imagen.
    """
    assert contenido.detectar_imagen(b"\x89PNG\r\n\x1a\n...") == ("image/png", "png")
    assert contenido.detectar_imagen(b"GIF89a...") == ("image/gif", "gif")
    assert contenido.detectar_imagen(b"<?php echo 1; ?>") is None
