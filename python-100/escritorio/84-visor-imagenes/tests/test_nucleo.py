"""Tests de la lógica del visor (Pillow, sin pantalla)."""
import pytest
from PIL import Image

from visor.nucleo import (ZOOM_MAX, ZOOM_MIN, ErrorImagen, Galeria, Vista, abrir, guardar_transformada,
                          info, listar, zoom_ajustado)


def test_listar_orden_natural(carpeta):
    """Solo extensiones de imagen (notas.txt no) y orden natural: img2 antes que img10 (orden
    alfabético puro pondría img10 primero).
    """
    assert [p.name for p in listar(carpeta)] == ["foto.jpg", "img2.png", "img10.png", "roto.png"]


def test_galeria_circular_y_desde_archivo(carpeta):
    """Galería desde un archivo empieza en él. Desde img10: +1 roto, +1 da la vuelta a foto, -1
    vuelve a roto. Quitar la actual deja la siguiente (foto). Galería vacía → None.
    """
    g = Galeria.desde(carpeta / "img10.png")
    assert g.actual.name == "img10.png"
    assert g.mover(1).name == "roto.png" and g.mover(1).name == "foto.jpg" and g.mover(-1).name == "roto.png"
    g.quitar_actual()
    assert g.actual.name == "foto.jpg" and len(g.rutas) == 3
    assert Galeria().mover(1) is None


def test_abrir_e_info(carpeta):
    """img2.png mide 40×20; un archivo que no es imagen lanza ErrorImagen (no la excepción
    cruda de Pillow).
    """
    im = abrir(carpeta / "img2.png")
    assert info(im, carpeta / "img2.png")["ancho"] == 40
    with pytest.raises(ErrorImagen):
        abrir(carpeta / "roto.png")


def test_abrir_aplica_orientacion_exif(tmp_path):
    """Foto 30×10 con EXIF Orientation=6 (cámara girada 90° horario): al abrirla se aplica la
    rotación y queda 10×30, como la muestran los celulares.
    """
    im = Image.new("RGB", (30, 10))
    exif = im.getexif()
    exif[0x0112] = 6  # Orientation = girar 90° horario
    im.save(tmp_path / "movil.jpg", exif=exif)
    assert abrir(tmp_path / "movil.jpg").size == (10, 30)


@pytest.mark.parametrize("img, caja, ampliar, esperado", [
    # Más ancha que la caja: factor = min(500/1000, 500/500) = 0.5.
    ((1000, 500), (500, 500), False, 0.5),
    # Más chica que la caja: sin ampliar se queda en 1.0; ampliando, min(500/100, 500/50) = 5.
    ((100, 50), (500, 500), False, 1.0), ((100, 50), (500, 500), True, 5.0),
    # Caso borde: ancho 0 no debe dividir por cero.
    ((0, 10), (10, 10), False, 1.0),
])
def test_zoom_ajustado(img, caja, ampliar, esperado):
    """1000×500 en caja 500×500 → 0.5 (limita el ancho). 100×50 sin ampliar → 1.0 (no agranda
    imágenes chicas); con ampliar → 5.0 (500/100). Imagen degenerada de ancho 0 → 1.0
    sin dividir por cero.
    """
    assert zoom_ajustado(*img, *caja, ampliar=ampliar) == esperado


def test_vista_zoom_limites_y_rotacion():
    """Muchos acercar/alejar topan en ZOOM_MAX/ZOOM_MIN. Rotar -90 da 270. 45° no está
    permitido.
    """
    v = Vista()
    for _ in range(50):
        v.acercar()
    assert v.zoom == ZOOM_MAX
    for _ in range(100):
        v.alejar()
    assert v.zoom == ZOOM_MIN
    v.rotar(-90)
    assert v.rotacion == 270
    with pytest.raises(ValueError):
        v.rotar(45)


def test_transformar_y_renderizar():
    """Imagen 4×2 con un píxel rojo en (0,0). Rotar 90° antihorario → 2×4 y el rojo baja a
    (0,3). Espejo horizontal → el rojo pasa a (3,0). Zoom 2.5 → 10×5.
    """
    im = Image.new("RGB", (4, 2))
    im.putpixel((0, 0), (255, 0, 0))  # rojo arriba a la izquierda
    v = Vista(rotacion=90)
    t = v.transformar(im)
    assert t.size == (2, 4) and t.getpixel((0, 3)) == (255, 0, 0)  # gira antihorario
    v = Vista(espejo_h=True)
    assert v.transformar(im).getpixel((3, 0)) == (255, 0, 0)
    v.zoom = 2.5
    assert v.renderizar(im).size == (10, 5)


def test_guardar_transformada_jpeg_quita_alfa(tmp_path):
    """JPEG no admite transparencia: una RGBA se convierte a RGB al guardar; la rotación de 90°
    convierte 6×3 en 3×6.
    """
    im = Image.new("RGBA", (6, 3))
    destino = guardar_transformada(im, Vista(rotacion=90), tmp_path / "salida.jpg")
    with Image.open(destino) as res:
        assert res.size == (3, 6) and res.mode == "RGB"
