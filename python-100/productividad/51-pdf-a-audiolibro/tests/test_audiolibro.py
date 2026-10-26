"""Tests con un PDF generado en el momento y un motor de voz falso."""
import pytest

from audiolibro import Convertidor, extraer_texto, limpiar_texto, trocear
from audiolibro.cli import ejecutar
from pdf_fixture import crear_pdf


# Falla las primeras `fallos` llamadas y luego devuelve un "MP3" falso que empieza con ID3.
class MotorFalso:
    def __init__(self, fallos=0):
        self.textos, self.fallos = [], fallos

    def sintetizar(self, texto, idioma):
        if self.fallos:
            self.fallos -= 1
            raise ConnectionError("sin red")
        self.textos.append((texto, idioma))
        return b"ID3" + texto.encode()[:5]


@pytest.fixture
# PDF de 3 páginas creado en el momento: dos con texto y una en blanco.
def pdf(tmp_path):
    ruta = tmp_path / "libro.pdf"
    ruta.write_bytes(crear_pdf([
        [(72, 720, "Capitulo uno. Habia una vez un gato."), (72, 700, "Fin del capitulo.")],
        [(72, 720, "Capitulo dos. El gato volvio.")],
        [],  # página en blanco
    ]))
    return ruta


# Todas las páginas, una página puntual (2..2) y un rango invertido.
def test_extraer(pdf):
    paginas = extraer_texto(pdf)
    assert len(paginas) == 3 and "Habia una vez" in paginas[0]
    assert extraer_texto(pdf, 2, 2)[0].startswith("Capitulo dos")
    with pytest.raises(ValueError):
        extraer_texto(pdf, 3, 1)


# Guion de corte, espacios dobles, salto simple y párrafo conservado.
def test_limpiar():
    assert limpiar_texto("compu-\ntadora  muy\nrápida\n\nOtro párrafo") == "computadora muy rápida\n\nOtro párrafo"


# Ningún trozo supera 100, el primero cierra en una oración y no se pierde ninguna palabra.
def test_trocear_respeta_maximo_y_oraciones():
    texto = "Una oración corta. " * 30 + "palabra " * 200
    trozos = trocear(texto, 100)
    assert all(len(t) <= 100 for t in trozos)
    assert trozos[0].endswith(".")
    assert " ".join(trozos).split() == texto.split()  # no se pierde ninguna palabra


# Crea la carpeta "out" y usa el idioma por defecto "es".
def test_pdf_a_mp3_unico(pdf, tmp_path):
    m = MotorFalso()
    [salida] = Convertidor(m).pdf_a_mp3(pdf, tmp_path / "out" / "libro.mp3")
    assert salida.read_bytes().startswith(b"ID3") and m.textos[0][1] == "es"


# La página 3 está en blanco: sólo salen p001 y p002.
def test_por_pagina_saltea_blancas(pdf, tmp_path):
    salidas = Convertidor(MotorFalso()).pdf_a_mp3(pdf, tmp_path / "l.mp3", por_pagina=True)
    assert [s.name for s in salidas] == ["l_p001.mp3", "l_p002.mp3"]


# 2 fallos → esperas de 1 y 2 s (lineales) y luego éxito; con 5 fallos y 2 intentos se propaga el error.
def test_reintentos():
    esperas = []
    conv = Convertidor(MotorFalso(fallos=2), dormir=esperas.append, pausa_reintento=1)
    assert conv._sintetizar_con_reintentos("hola") == b"ID3hola"
    assert esperas == [1, 2]
    with pytest.raises(ConnectionError):
        Convertidor(MotorFalso(fallos=5), reintentos=2, dormir=lambda s: None)._sintetizar_con_reintentos("x")


# Sólo espacios → ValueError en vez de un MP3 vacío.
def test_texto_vacio(tmp_path):
    with pytest.raises(ValueError):
        Convertidor(MotorFalso()).texto_a_mp3("   ", tmp_path / "x.mp3")


# Idioma en inglés y página inicial (9) fuera del PDF → exit 1.
def test_cli(pdf, tmp_path, capsys):
    assert ejecutar([str(pdf), "-o", str(tmp_path / "a.mp3"), "--idioma", "en"], MotorFalso()) == 0
    assert "Generado" in capsys.readouterr().out
    assert ejecutar([str(pdf), "--desde", "9"], MotorFalso()) == 1
