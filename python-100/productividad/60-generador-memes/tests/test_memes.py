"""Tests con imágenes sintéticas y la fuente que trae Pillow (determinista)."""
from PIL import Image, ImageFont

from memes import EstiloMeme, ajustar_texto, crear_meme
from memes.cli import ejecutar

# Fuente que trae Pillow: igual en cualquier máquina.
CARGAR = lambda t: ImageFont.load_default(size=t)


def colores(img, caja):
    """Conjunto de colores presentes en una región de la imagen."""
    return {c for _, c in img.crop(caja).getcolors(1 << 20)}


# Corte por ancho en píxeles, palabra larga sola en su línea y saltos de línea respetados.
def test_ajustar_texto_por_pixeles():
    f = CARGAR(20)
    lineas = ajustar_texto("uno dos tres cuatro cinco seis siete", f, 120)
    assert len(lineas) > 1 and all(f.getbbox(l)[2] <= 120 for l in lineas)
    assert ajustar_texto("supercalifragilístico", f, 10) == ["supercalifragilístico"]
    assert ajustar_texto("a\nb", f, 500) == ["a", "b"]


# Arriba y abajo hay blanco y negro (texto + contorno); el centro queda verde; el original no se modifica.
def test_meme_texto_arriba_y_abajo():
    base = Image.new("RGB", (400, 300), (0, 128, 0))
    m = crear_meme(base, "hola", "chau", cargar=CARGAR)
    assert m.size == base.size and base.getpixel((200, 20)) == (0, 128, 0)  # original intacto
    sup, med, inf = colores(m, (0, 0, 400, 80)), colores(m, (0, 120, 400, 180)), colores(m, (0, 220, 400, 300))
    assert (255, 255, 255) in sup and (0, 0, 0) in sup   # texto blanco + contorno negro
    assert (255, 255, 255) in inf
    assert med == {(0, 128, 0)}                          # el centro queda libre


# Imagen de 300 px → tamaño inicial 30; un texto larguísimo obliga a achicar.
def test_texto_largo_achica_fuente():
    usados = []
    def cargar(t):
        usados.append(t)
        return CARGAR(t)
    crear_meme(Image.new("RGB", (300, 300)), "palabra " * 40, cargar=cargar)
    assert usados[0] == 30 and usados[-1] < usados[0]


# Una imagen RGBA se convierte a RGB (JPG no admite transparencia).
def test_png_transparente_y_solo_abajo():
    m = crear_meme(Image.new("RGBA", (200, 200), (0, 0, 0, 0)), abajo="x", estilo=EstiloMeme(mayusculas=False),
                   cargar=CARGAR)
    assert m.mode == "RGB"


# Salida por defecto *_meme.jpg, sin textos (exit 2) e imagen corrupta (exit 1).
def test_cli(tmp_path, capsys):
    ruta = tmp_path / "foto.png"
    Image.new("RGB", (320, 240), "navy").save(ruta)
    assert ejecutar([str(ruta), "-a", "cuando los tests", "-b", "pasan"]) == 0
    assert (tmp_path / "foto_meme.jpg").exists()
    assert ejecutar([str(ruta)]) == 2
    (tmp_path / "rota.png").write_text("no soy imagen")
    assert ejecutar([str(tmp_path / "rota.png"), "-a", "x"]) == 1
