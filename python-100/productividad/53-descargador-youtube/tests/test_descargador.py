"""Tests con backend falso: no se contacta a YouTube."""
import pytest

from descargador import Descargador, Formato, InfoVideo, elegir_formato, nombre_seguro, validar_url
from descargador.cli import ejecutar

# Formatos típicos: dos progresivos (360p, 720p), dos de sólo video 1080p y dos de sólo audio.
F = (
    Formato("18", "mp4", 360, True, True, 500),
    Formato("22", "mp4", 720, True, True, 1500),
    Formato("137", "mp4", 1080, False, True, 4000),
    Formato("248", "webm", 1080, False, True, 3500),
    Formato("140", "m4a", None, True, False, 128),
    Formato("251", "webm", None, True, False, 160),
)
# Título con caracteres prohibidos en nombres de archivo.
INFO = InfoVideo("dQw4w9WgXcQ", 'Mi video: "prueba" / 2026', 212, F)
URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


# Simula el backend: reporta progreso, escribe un archivo falso y anota qué formatos se pidieron.
class BackendFalso:
    def __init__(self):
        self.descargas = []

    def obtener_info(self, url):
        return INFO

    def descargar(self, url, formatos, destino, progreso):
        if progreso:
            progreso(50, 100); progreso(100, 100)
        destino.write_bytes(b"video")
        self.descargas.append([f.id for f in formatos])
        return destino


# Formatos aceptados: watch?v=, youtu.be, shorts y m. con parámetros extra.
@pytest.mark.parametrize("url", [URL, "https://youtu.be/dQw4w9WgXcQ", "https://www.youtube.com/shorts/dQw4w9WgXcQ",
                                 "https://m.youtube.com/watch?v=dQw4w9WgXcQ&t=10"])
def test_urls_validas(url):
    assert validar_url(url) == "dQw4w9WgXcQ"


# Otro sitio, dominio que imita a YouTube, esquema no http(s) e ID de longitud inválida.
@pytest.mark.parametrize("url", ["https://vimeo.com/123", "https://youtube.com.malicioso.net/watch?v=dQw4w9WgXcQ",
                                 "ftp://youtube.com/watch?v=dQw4w9WgXcQ", "https://www.youtube.com/watch?v=corto"])
def test_urls_invalidas(url):
    with pytest.raises(ValueError):
        validar_url(url)


# Cubre progresivo, combinación mp4 + mejor audio, sólo audio, tope intermedio, tope demasiado bajo y calidad inválida.
def test_elegir_formatos():
    assert [f.id for f in elegir_formato(F, "720p")] == ["22"]          # progresivo
    assert [f.id for f in elegir_formato(F, "mejor")] == ["137", "251"]  # video mp4 + mejor audio
    assert [f.id for f in elegir_formato(F, "audio")] == ["251"]
    assert [f.id for f in elegir_formato(F, "480")] == ["18"]           # mayor que no supera
    assert [f.id for f in elegir_formato(F, "144p")] == ["18"]          # nada menor: el más chico
    with pytest.raises(ValueError):
        elegir_formato(F, "altísima")


# Caracteres prohibidos, título que queda vacío y recorte a 120 + ".mp4" = 124.
def test_nombre_seguro():
    assert nombre_seguro('Mi video: "prueba" / 2026', "mp4") == "Mi video_ _prueba_ _ 2026.mp4"
    assert nombre_seguro("...", "mp3") == "video.mp3"
    assert len(nombre_seguro("a" * 500, "mp4")) == 124


# La extensión sale del formato de audio (webm); la segunda descarga choca con la primera.
def test_descargar(tmp_path):
    b = BackendFalso()
    ruta = Descargador(b).descargar(URL, "audio", tmp_path)
    assert ruta.name.endswith(".webm") and b.descargas == [["251"]]
    with pytest.raises(FileExistsError):
        Descargador(b).descargar(URL, "audio", tmp_path)


# --info lista formatos, la descarga muestra el aviso legal y una URL ajena da exit 1.
def test_cli(tmp_path, capsys):
    assert ejecutar([URL, "--info"], BackendFalso()) == 0
    assert "1080p (sin audio)" in capsys.readouterr().out
    assert ejecutar([URL, "-c", "720p", "-o", str(tmp_path)], BackendFalso()) == 0
    assert "Términos" in capsys.readouterr().err
    assert ejecutar(["https://otro.com/x"], BackendFalso()) == 1
