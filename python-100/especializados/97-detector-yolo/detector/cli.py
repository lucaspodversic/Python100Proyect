"""CLI: detecta en una imagen o carpeta, guarda imágenes anotadas y un JSON.

    python -m detector fotos/ --salida anotadas/ --conf 0.4 --clases person,car
    python -m detector demo --salida demo/      # escena sintética + detector falso
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

from .dibujo import anotar
from .modelo import COLORES_FALSOS, crear_detector
from .postproceso import contar, filtrar, nms

EXTENSIONES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def escena_demo(ancho: int = 320, alto: int = 240) -> Image.Image:
    """Imagen sintética con figuras de los colores que reconoce el detector falso."""
    im = Image.new("RGB", (ancho, alto), (200, 200, 200))
    d = ImageDraw.Draw(im)
    d.rectangle([20, 40, 60, 140], fill=COLORES_FALSOS["persona"])
    d.rectangle([100, 120, 220, 180], fill=COLORES_FALSOS["auto"])
    d.ellipse([240, 150, 300, 200], fill=COLORES_FALSOS["perro"])
    d.rectangle([70, 50, 95, 130], fill=COLORES_FALSOS["persona"])
    return im


def main(argv: list[str] | None = None) -> int:
    """Procesa una imagen, todas las imágenes de una carpeta (ignora lo que no es imagen) o la
    escena 'demo' (que siempre usa el detector falso). Por imagen: detecta, filtra por
    confianza y clases, aplica NMS, guarda la imagen anotada y acumula detecciones y
    conteo en detecciones.json.
    """
    ap = argparse.ArgumentParser(prog="detector")
    ap.add_argument("entrada", help="imagen, carpeta o 'demo'")
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--falso", action="store_true", help="usar el detector falso (sin ultralytics)")
    ap.add_argument("--pesos", default="yolo11n.pt")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--clases", default="", help="lista separada por comas")
    a = ap.parse_args(argv)

    if a.entrada == "demo":
        imagenes = [("demo.png", escena_demo())]
        a.falso = True
    else:
        ruta = Path(a.entrada)
        archivos = sorted(p for p in ruta.iterdir() if p.suffix.lower() in EXTENSIONES) if ruta.is_dir() else [ruta]
        if not archivos or not all(p.exists() for p in archivos):
            ap.error(f"no hay imágenes en {ruta}")
        imagenes = [(p.name, Image.open(p)) for p in archivos]
    try:
        det = crear_detector(a.falso) if a.falso else crear_detector(False, pesos=a.pesos, confianza=a.conf)
    except RuntimeError as e:
        print(f"error: {e}")
        return 2
    clases = {c.strip() for c in a.clases.split(",") if c.strip()} or None
    a.salida.mkdir(parents=True, exist_ok=True)
    informe = {}
    for nombre, im in imagenes:
        dets = nms(filtrar(det.detectar(im), a.conf, clases), a.iou)
        anotar(im, dets).save(a.salida / f"{Path(nombre).stem}_anotada.png")
        informe[nombre] = {"conteo": contar(dets), "detecciones": [d.a_dict() for d in dets]}
        print(f"{nombre}: {contar(dets) or 'sin detecciones'}")
    (a.salida / "detecciones.json").write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0
