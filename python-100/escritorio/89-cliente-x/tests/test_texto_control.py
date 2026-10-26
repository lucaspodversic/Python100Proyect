"""Tests del conteo de caracteres, la división en hilos y el controlador (sin Tk ni red)."""
import pytest

from clientex.api import ErrorLimite, Post, ServicioFalso
from clientex.control import Controlador
from clientex.texto import LIMITE, dividir_en_hilo, longitud, validar


def test_longitud_urls_y_pesos():
    """Toda URL cuenta 23 caracteres sin importar su largo; CJK pesa 2; 'é' compuesta y
    descompuesta cuenta 1 tras normalizar a NFC.
    """
    assert longitud("hola") == 4
    assert longitud("mirá https://example.com/" + "x" * 100) == len("mirá ") + 23
    assert longitud("日本") == 4          # CJK pesa 2
    assert longitud("é") == longitud("e\u0301") == 1  # NFC


def test_validar():
    """Exactamente LIMITE pasa; uno más no; solo espacios tampoco."""
    validar("x" * LIMITE)
    with pytest.raises(ValueError):
        validar("x" * (LIMITE + 1))
    with pytest.raises(ValueError):
        validar("   ")


def test_hilo_respeta_limite_y_numera():
    """150 palabras (~1300 caracteres) se parten en varios posts que respetan el límite,
    numerados (1/n), y se pueden reconstruir.
    """
    texto = " ".join(f"palabra{i}" for i in range(150))
    partes = dividir_en_hilo(texto)
    assert len(partes) > 1
    assert all(longitud(p) <= LIMITE for p in partes)
    assert partes[0].endswith(f"(1/{len(partes)})")
    # Reconstruir quitando sufijos devuelve el texto original.
    assert " ".join(p.rsplit(" (", 1)[0] for p in partes) == texto


def test_hilo_corto_y_palabra_gigante():
    """Un texto corto no se numera; una 'palabra' de 600 caracteres se corta a la fuerza."""
    assert dividir_en_hilo("hola") == ["hola"]
    partes = dividir_en_hilo("a" * 600)
    assert all(longitud(p) <= LIMITE for p in partes)


def crear():
    """Servicio falso con 2 posts de 'demo' y 1 de 'otro', más el controlador y un registro de
    redibujos.
    """
    s = ServicioFalso(posts=[Post("1", "uno python", "demo"), Post("2", "dos", "demo"), Post("3", "tres", "otro")])
    cambios = []
    return s, Controlador(s, al_cambiar=lambda: cambios.append(1)), cambios


def test_conectar_carga_propias_y_paginacion():
    """Conectar carga solo los posts de 'demo' (ids 1 y 2), sin más páginas, y avisa a la
    vista.
    """
    s, c, cambios = crear()
    c.conectar()
    assert c.usuario["username"] == "demo" and [p.id for p in c.posts] == ["1", "2"]
    assert c.cursor is None and cambios


def test_buscar_y_mas():
    """Con páginas de 1, 'python' encuentra el 1 y 'Cargar más' agrega el 4."""
    s, c, _ = crear()
    s.tam_pagina = 1
    s.posts.append(Post("4", "otro python", "x"))
    c.buscar("python")
    assert len(c.posts) == 1 and c.cursor
    c.mas()
    assert [p.id for p in c.posts] == ["1", "4"]


def test_publicar_hilo_encadena_respuestas():
    """La primera parte no responde a nada y cada siguiente responde a la anterior."""
    s, c, _ = crear()
    respuestas = []
    original = s.publicar
    s.publicar = lambda t, r=None: (respuestas.append(r), original(t, r))[1]
    assert c.publicar(" ".join(["bla"] * 200), como_hilo=True)
    assert respuestas[0] is None and all(respuestas[1:])
    assert c.mensaje.startswith("Publicado")


def test_publicar_invalido_no_llama_api():
    """300 caracteres sin hilo: se rechaza localmente y no se publica nada."""
    s, c, _ = crear()
    assert not c.publicar("x" * 300)
    assert "excede" in c.mensaje and len(s.posts) == 3


def test_error_se_muestra():
    """Un límite de 30 s se muestra en el estado y libera 'ocupado'."""
    s, c, _ = crear()
    s.fallo = ErrorLimite(30)
    c.conectar()
    assert "30 s" in c.mensaje and not c.ocupado
