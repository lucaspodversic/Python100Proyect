"""Tests de regiones, nombres y guardado. Fecha fija para que los nombres sean deterministas."""
from datetime import datetime

import pytest
from PIL import Image

from captura.archivos import Sesion, generar_nombre, guardar, ruta_libre, sanear
from captura.capturador import CapturadorFalso, ErrorCaptura, Region

AHORA = datetime(2026, 10, 26, 9, 5, 7)


def test_region_desde_puntos_normaliza():
    """Puntos invertidos (100,80)→(10,20) dan x=10, y=20, 90×60; la caja de Pillow es (izq,
    arriba, der, abajo) = (10, 20, 100, 80). 1 px de ancho no es una región válida.
    """
    assert Region.desde_puntos(100, 80, 10, 20) == Region(10, 20, 90, 60)
    assert Region(10, 20, 90, 60).caja() == (10, 20, 100, 80)
    assert not Region(0, 0, 1, 50).valida()


def test_falso_es_determinista_y_recorta():
    """Dos capturas iguales byte a byte; un recorte en (50,50) empieza en el cuadrado rojo; una
    región que se sale de los 320 px de ancho (300+50) da error.
    """
    c = CapturadorFalso()
    a, b = c.capturar(), c.capturar()
    assert a.tobytes() == b.tobytes() and a.size == (320, 200)
    r = c.capturar(Region(50, 50, 10, 10))
    assert r.size == (10, 10) and r.getpixel((0, 0)) == (255, 0, 0)
    with pytest.raises(ErrorCaptura):
        c.capturar(Region(300, 0, 50, 10))


@pytest.mark.parametrize("entrada, esperado", [
    # Separadores y caracteres prohibidos en Windows (/ : * ?) → "_".
    ("hola/mundo", "hola_mundo"), ("a:b*c?", "a_b_c_"),
    # Puntos y espacios en los bordes se quitan (Windows los ignora; un punto inicial oculta en Unix).
    ("  ..oculto. ", "oculto"),
    # Nombre reservado de Windows (CON, NUL, COM1…) → se antepone "_"; vacío → nombre por defecto.
    ("CON", "_CON"), ("", "captura"),
    # Path traversal: las barras se reemplazan, así que el archivo nunca sale de la carpeta elegida.
    ("../../etc/passwd", "_.._etc_passwd"),
])
def test_sanear(entrada, esperado):
    """Ver la tabla: caracteres inválidos en Windows, nombres reservados, puntos y espacios en
    los bordes, vacío y path traversal.
    """
    assert sanear(entrada) == esperado


def test_generar_nombre():
    """Fecha 2026-10-26 09:05:07 con formato strftime; {n:03d} rellena con ceros; un campo
    desconocido es error.
    """
    assert generar_nombre("captura_{fecha:%Y%m%d_%H%M%S}", 1, (10, 10), AHORA) == "captura_20261026_090507"
    assert generar_nombre("{n:03d}-{ancho}x{alto}", 7, (320, 200), AHORA) == "007-320x200"
    with pytest.raises(ValueError):
        generar_nombre("{desconocido}", 1, (1, 1), AHORA)


def test_ruta_libre_no_sobrescribe(tmp_path):
    """Si existen a.png y a-2.png, la siguiente libre es a-3.png."""
    (tmp_path / "a.png").write_bytes(b"x")
    (tmp_path / "a-2.png").write_bytes(b"x")
    assert ruta_libre(tmp_path, "a", "png").name == "a-3.png"


# Firmas: PNG = 89 'PNG'; JPEG = FF D8 (SOI); WebP = contenedor 'RIFF'; BMP = 'BM'.
@pytest.mark.parametrize("fmt, firma", [("png", b"\x89PNG"), ("jpg", b"\xff\xd8"), ("webp", b"RIFF"), ("bmp", b"BM")])
def test_guardar_formatos(tmp_path, fmt, firma):
    """Cada formato empieza con su firma ('magic number'). RGBA se convierte para JPG (que no
    tiene alfa) y no quedan temporales.
    """
    ruta = guardar(Image.new("RGBA", (4, 4)), tmp_path / "sub", "x", fmt)
    assert ruta.read_bytes().startswith(firma)
    assert [p.name for p in ruta.parent.iterdir()] == [f"x.{fmt}"]  # sin temporales


def test_guardar_formato_invalido(tmp_path):
    """GIF no está entre los formatos permitidos."""
    with pytest.raises(ValueError):
        guardar(Image.new("RGB", (1, 1)), tmp_path, "x", "gif")


def test_sesion_nombre_personalizado_y_plantilla(tmp_path):
    """Sin nombre se usa la plantilla (cap_01). El nombre personalizado se sanea (':' → '_') y
    si se repite se le agrega -2 en vez de sobrescribir.
    """
    s = Sesion(CapturadorFalso(), tmp_path, plantilla="cap_{n:02d}", ahora=lambda: AHORA)
    r1 = s.capturar_y_guardar()
    r2 = s.capturar_y_guardar(Region(0, 0, 20, 10), nombre="Mi factura: octubre")
    r3 = s.capturar_y_guardar(nombre="Mi factura: octubre")
    assert [r.name for r in (r1, r2, r3)] == ["cap_01.png", "Mi factura_ octubre.png", "Mi factura_ octubre-2.png"]
    assert Image.open(r2).size == (20, 10)
    assert s.historial == [r1, r2, r3]
