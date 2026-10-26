"""Tests offline: usan el detector falso sobre escenas sintéticas; ultralytics no se instala ni
se descarga nada.
"""
import json
import sys

import pytest
from PIL import Image, ImageDraw

from detector.cli import escena_demo, main
from detector.dibujo import anotar, color_clase
from detector.modelo import Caja, Deteccion, DetectorFalso, DetectorYOLO
from detector.postproceso import contar, filtrar, iou, nms
from detector.seguimiento import Rastreador


def D(clase, conf, *c):
    """Atajo para construir una detección: D(clase, conf, x1, y1, x2, y2)."""
    return Deteccion(clase, conf, Caja(*c))


def test_caja_e_iou():
    """Dos cajas de 10x10 desplazadas 5 px: intersección 50, unión 100+100-50 = 150 → IoU 1/3.
    Una caja consigo misma da 1 y con una disjunta 0. Una caja invertida es un error.
    """
    a, b = Caja(0, 0, 10, 10), Caja(5, 0, 15, 10)
    assert a.area == 100 and a.centro == (5, 5)
    assert iou(a, b) == pytest.approx(50 / 150)
    assert iou(a, a) == 1 and iou(a, Caja(20, 20, 30, 30)) == 0
    with pytest.raises(ValueError):
        Caja(10, 0, 0, 10)


def test_nms_por_clase():
    """Los dos autos de arriba se superponen con IoU 81/119 ≈ 0.68 > 0.5, así que se elimina el
    de menor confianza (0.8). La persona en el mismo lugar sobrevive porque NMS es por
    clase; el auto lejano (0.6) no se superpone. Sin separar por clase, la persona
    también se suprime → quedan 2.
    """
    dets = [D("auto", 0.9, 0, 0, 10, 10), D("auto", 0.8, 1, 1, 11, 11), D("persona", 0.7, 1, 1, 11, 11),
            D("auto", 0.6, 50, 50, 60, 60)]
    r = nms(dets, 0.5)
    assert [(d.clase, d.confianza) for d in r] == [("auto", 0.9), ("persona", 0.7), ("auto", 0.6)]
    assert len(nms(dets, 0.5, por_clase=False)) == 2


def test_filtrar_y_contar():
    """Confianza >= 0.3 deja 2; filtrar por clase; área >= 50 deja solo la caja de 10x10 (las
    otras son de 4 y 25).
    """
    dets = [D("auto", 0.9, 0, 0, 10, 10), D("perro", 0.2, 0, 0, 2, 2), D("auto", 0.5, 0, 0, 5, 5)]
    assert len(filtrar(dets, confianza=0.3)) == 2
    assert filtrar(dets, clases={"perro"})[0].clase == "perro"
    assert len(filtrar(dets, area_minima=50)) == 1
    assert contar(dets) == {"auto": 2, "perro": 1}


def test_detector_falso_en_escena():
    """La escena demo tiene 1 auto (rectángulo de 100,120 a 220,180 inclusive → x2/y2
    exclusivos 221,181), 1 perro (elipse) y 2 personas. La elipse es menos sólida que un
    rectángulo, así que tiene menos confianza.
    """
    dets = DetectorFalso().detectar(escena_demo())
    assert contar(dets) == {"auto": 1, "perro": 1, "persona": 2}
    auto = next(d for d in dets if d.clase == "auto")
    assert (auto.caja.x1, auto.caja.y1, auto.caja.x2, auto.caja.y2) == (100, 120, 221, 181)
    assert all(0.5 <= d.confianza <= 0.99 for d in dets)
    perro = next(d for d in dets if d.clase == "perro")
    assert perro.confianza < auto.confianza   # la elipse es menos "sólida" que un rectángulo


def test_detector_falso_ignora_ruido():
    """Un cuadrado de 3x3 = 9 px está por debajo del área mínima (25)."""
    im = Image.new("RGB", (50, 50), "white")
    ImageDraw.Draw(im).rectangle([10, 10, 12, 12], fill=(255, 0, 0))  # 9 px < área mínima
    assert DetectorFalso().detectar(im) == []


def test_anotar():
    """La salida es una copia del mismo tamaño y el borde inferior izquierdo de la primera caja
    tiene el color de su clase. El color de cada clase es estable y distinto entre
    clases.
    """
    im = escena_demo()
    dets = DetectorFalso().detectar(im)
    out = anotar(im, dets)
    assert out.size == im.size and out is not im
    c = dets[0].caja
    assert out.getpixel((int(c.x1), int(c.y2) - 1)) == color_clase(dets[0].clase)  # borde de la caja
    assert color_clase("auto") == color_clase("auto") != color_clase("persona")


def test_rastreador_ids_y_cruces():
    """La persona y el auto conservan los ids 1 y 2 durante 6 cuadros; la persona cruza la
    línea una sola vez bajando. Sin detecciones durante 2 cuadros (> max_perdidos = 1)
    las pistas se olvidan, y un objeto nuevo recibe el id 3 (no se reutilizan).
    """
    r = Rastreador(linea_y=100, max_perdidos=1)
    # Una persona de 20x40 px que baja 10 px por cuadro (IoU entre cuadros = 600/1000 = 0.6,
    # por encima del umbral 0.3) y un auto quieto. El centro y = 60 + 10k cruza la línea 100 en k = 4.
    for k in range(6):
        activos = r.actualizar([D("persona", 0.9, 10, 40 + 10 * k, 30, 80 + 10 * k), D("auto", 0.9, 200, 10, 260, 40)])
        assert sorted(p.id for p in activos) == [1, 2]
    assert r.cruces == {"bajando": 1, "subiendo": 0}
    assert len(r.pistas[1].historial) == 6
    r.actualizar([]); r.actualizar([])
    assert r.pistas == {}             # se olvidan tras max_perdidos
    assert [p.id for p in r.actualizar([D("auto", 0.9, 0, 0, 5, 5)])] == [3]


def test_yolo_sin_ultralytics_da_error_claro(monkeypatch):
    """Poner None en sys.modules hace que el import falle como si el paquete no estuviera
    instalado.
    """
    monkeypatch.setitem(sys.modules, "ultralytics", None)   # simula que no está instalado
    with pytest.raises(RuntimeError, match="ultralytics"):
        DetectorYOLO()


def test_cli_demo(tmp_path, capsys):
    """El modo demo escribe el JSON con el conteo esperado de la escena y la imagen anotada."""
    assert main(["demo", "--salida", str(tmp_path)]) == 0
    datos = json.loads((tmp_path / "detecciones.json").read_text())
    assert datos["demo.png"]["conteo"] == {"auto": 1, "perro": 1, "persona": 2}
    assert (tmp_path / "demo_anotada.png").exists()


def test_cli_carpeta_con_filtro_de_clases(tmp_path):
    """Una carpeta con una imagen y un .txt: el .txt se ignora y --clases persona deja solo las
    2 personas.
    """
    entrada = tmp_path / "in"; entrada.mkdir()
    escena_demo().save(entrada / "a.png")
    (entrada / "nota.txt").write_text("x")
    assert main([str(entrada), "--salida", str(tmp_path / "out"), "--falso", "--clases", "persona"]) == 0
    datos = json.loads((tmp_path / "out" / "detecciones.json").read_text())
    assert datos["a.png"]["conteo"] == {"persona": 2}
