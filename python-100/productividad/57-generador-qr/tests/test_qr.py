"""Tests de payloads y de imágenes generadas (en tmp_path)."""
import pytest
from PIL import Image

from generador_qr import (OpcionesQR, contenido_email, contenido_vcard, contenido_wifi,
                          generar_imagen, guardar, matriz)
from generador_qr.cli import ejecutar


# Escapado de ; : " — red abierta y oculta — sin clave o con seguridad inválida → error.
def test_wifi_escapado():
    assert contenido_wifi('Mi;Red', 'cla:ve"1') == 'WIFI:T:WPA;S:Mi\\;Red;P:cla\\:ve\\"1;;'
    assert contenido_wifi("Libre", seguridad="nopass", oculta=True) == "WIFI:T:nopass;S:Libre;H:true;;"
    with pytest.raises(ValueError):
        contenido_wifi("x")
    with pytest.raises(ValueError):
        contenido_wifi("x", "y", "WPA9")


# Coma escapada en ORG; espacio codificado como %20; sin asunto no hay "?".
def test_vcard_y_email():
    v = contenido_vcard("Ana", "Pérez", "+54911", organizacion="ACME, S.A.")
    assert "N:Pérez;Ana;;;" in v and "ORG:ACME\\, S.A." in v and v.endswith("END:VCARD")
    assert contenido_email("a@b.com", "Hola mundo") == "mailto:a@b.com?subject=Hola%20mundo"
    assert contenido_email("a@b.com") == "mailto:a@b.com"


# "hola" entra en la versión 1 (21×21); la esquina tiene el buscador: fila negra de 7 y luego blanco por dentro.
def test_matriz_patrones_de_posicion():
    m = matriz("hola", OpcionesQR(borde=0))
    assert len(m) == 21 and all(len(f) == 21 for f in m)  # versión 1
    assert m[0][:7] == [True] * 7 and m[1][1:6] == [False] * 5  # buscador sup-izq


# Tamaño = módulos × píxeles por módulo; la esquina es fondo blanco (borde) y aparece el rojo pedido.
def test_imagen_colores_y_tamano():
    img = generar_imagen("https://ejemplo.org", OpcionesQR(tamano_modulo=5, color="#ff0000"))
    n = len(matriz("https://ejemplo.org"))
    assert img.size == (n * 5, n * 5)
    assert img.getpixel((0, 0)) == (255, 255, 255)
    assert (255, 0, 0) in {c for _, c in img.getcolors(1 << 16)}


# El centro tiene el color del logo; el ancho coincide con un QR de nivel H; el SVG con logo es error.
def test_logo_fuerza_correccion_alta(tmp_path):
    logo = tmp_path / "logo.png"
    Image.new("RGBA", (50, 50), (0, 128, 255, 255)).save(logo)
    img = generar_imagen("texto", OpcionesQR(logo=logo))
    assert img.getpixel((img.width // 2, img.height // 2)) == (0, 128, 255)
    assert len(matriz("texto", OpcionesQR(correccion="H"))) * 10 == img.width
    with pytest.raises(ValueError):
        guardar("texto", tmp_path / "x.svg", OpcionesQR(logo=logo))


# PNG real según la extensión, SVG como texto y contenido vacío → error.
def test_guardar_formatos(tmp_path):
    assert Image.open(guardar("a", tmp_path / "a.png")).format == "PNG"
    assert "<svg" in guardar("a", tmp_path / "a.svg").read_text()
    with pytest.raises(ValueError):
        generar_imagen("")


# Vista previa ASCII, guardado WiFi a PNG y red protegida sin clave (exit 1).
def test_cli(tmp_path, capsys):
    assert ejecutar(["texto", "hola"]) == 0
    assert "██" in capsys.readouterr().out
    assert ejecutar(["-o", str(tmp_path / "w.png"), "wifi", "Casa", "--clave", "1234"]) == 0
    assert (tmp_path / "w.png").exists()
    assert ejecutar(["wifi", "Casa"]) == 1
