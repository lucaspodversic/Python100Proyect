"""Tests sobre carpetas temporales."""
import json
from pathlib import Path

import pytest

from organizador import Organizador, Regla, destino_para
from organizador.cli import ejecutar
from organizador.motor import ruta_libre


def crear(carpeta: Path, *nombres: str) -> None:
    """Crea archivos de prueba con contenido mínimo."""
    for n in nombres:
        (carpeta / n).write_text("x")


# Mayúsculas en la extensión, regla con patrón, PDF genérico, sin regla, temporal y oculto.
@pytest.mark.parametrize("nombre,esperado", [
    ("foto.JPG", "Imagenes"), ("Factura_Enero.pdf", "Facturas"), ("manual.pdf", "Documentos"),
    ("datos.csv", "Planillas"), ("raro.xyz", "Otros"), ("bajando.crdownload", None), (".oculto", None),
])
def test_destino(nombre, esperado):
    assert destino_para(Path(nombre)) == esperado


# Ya existe Imagenes/a.png: el nuevo se renombra a "a (1).png" y el viejo queda intacto.
def test_organizar_y_conflictos(tmp_path):
    crear(tmp_path, "a.png", "b.mp3", "c.zip")
    (tmp_path / "Imagenes").mkdir(); (tmp_path / "Imagenes" / "a.png").write_text("viejo")
    movs = Organizador(tmp_path).organizar()
    assert len(movs) == 3
    assert (tmp_path / "Imagenes" / "a (1).png").exists()  # no se pisó el existente
    assert (tmp_path / "Imagenes" / "a.png").read_text() == "viejo"
    assert (tmp_path / "Musica" / "b.mp3").exists()


# Se informa el movimiento pero el archivo sigue en su lugar.
def test_simulacion_no_mueve(tmp_path):
    crear(tmp_path, "a.png")
    assert len(Organizador(tmp_path, simulacion=True).organizar()) == 1
    assert (tmp_path / "a.png").exists()


# 1.ª pasada: tamaño desconocido; 2.ª: cambió (1 → 4 bytes); 3.ª: igual que la anterior → se mueve.
def test_estabilidad(tmp_path):
    org = Organizador(tmp_path)
    crear(tmp_path, "video.mp4")
    assert org.organizar(exigir_estable=True) == []   # 1ª vez: se anota el tamaño
    (tmp_path / "video.mp4").write_text("xxxx")       # sigue creciendo
    assert org.organizar(exigir_estable=True) == []
    assert len(org.organizar(exigir_estable=True)) == 1  # ya estable


# Dos iteraciones: la primera anota el tamaño y la segunda mueve el archivo.
def test_vigilar(tmp_path):
    crear(tmp_path, "a.txt")
    assert Organizador(tmp_path).vigilar(0, iteraciones=2, dormir=lambda s: None) == 1


# Con por_defecto=None el archivo que no coincide con ninguna regla se queda donde está.
def test_reglas_personalizadas_y_sin_defecto(tmp_path):
    crear(tmp_path, "informe-q1.docx", "otro.bin")
    reglas = (Regla.desde_dict({"carpeta": "Informes", "extensiones": ["docx"], "patron": "^informe"}),)
    Organizador(tmp_path, reglas, por_defecto=None).organizar()
    assert (tmp_path / "Informes" / "informe-q1.docx").exists() and (tmp_path / "otro.bin").exists()


# Deshacer devuelve los 2 archivos, vacía el historial y un segundo deshacer no hace nada.
def test_deshacer(tmp_path):
    reg = tmp_path / ".organizador.json"
    crear(tmp_path, "a.png", "b.txt")
    org = Organizador(tmp_path, registro=reg)
    org.organizar()
    assert len(org.deshacer()) == 2
    assert (tmp_path / "a.png").exists() and json.loads(reg.read_text()) == []
    assert org.deshacer() == []


# "x.txt" y "x (1).txt" ocupados → "x (2).txt".
def test_ruta_libre(tmp_path):
    crear(tmp_path, "x.txt", "x (1).txt")
    assert ruta_libre(tmp_path / "x.txt").name == "x (2).txt"


# Simular, organizar, deshacer y carpeta inexistente (exit 1).
def test_cli(tmp_path, capsys):
    crear(tmp_path, "a.png")
    assert ejecutar([str(tmp_path), "--simular"]) == 0
    assert "Se moverían: 1" in capsys.readouterr().out
    assert ejecutar([str(tmp_path)]) == 0
    assert ejecutar([str(tmp_path), "--deshacer"]) == 0
    assert (tmp_path / "a.png").exists()
    assert ejecutar([str(tmp_path / "nada")]) == 1
