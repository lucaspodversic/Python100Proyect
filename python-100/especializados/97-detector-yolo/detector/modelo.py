"""Modelos de datos y backends de detección.

* :class:`Detector` es el *Protocol* que usa el resto del código: recibe una
  imagen de Pillow y devuelve una lista de :class:`Deteccion`.
* :class:`DetectorYOLO` usa **ultralytics** (YOLOv8/YOLO11). Se importa de forma
  perezosa: el paquete funciona y se testea sin tenerlo instalado.
* :class:`DetectorFalso` es determinista y sin red: encuentra regiones de
  colores puros (rojo → "persona", azul → "auto", verde → "perro") mediante
  componentes conexas. Sirve para tests, demos y para desarrollar la UI sin GPU.
"""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from typing import Protocol

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class Caja:
    """Rectángulo (x1, y1, x2, y2) en píxeles con x2/y2 exclusivos, así el área es simplemente
    ancho × alto. Rechaza cajas invertidas.
    """
    x1: float
    y1: float
    x2: float
    y2: float

    def __post_init__(self) -> None:
        """Valida que x1 <= x2 y y1 <= y2 (las cajas de área cero se permiten)."""
        if self.x2 < self.x1 or self.y2 < self.y1:
            raise ValueError(f"caja inválida: {self}")

    @property
    def area(self) -> float:
        """Ancho × alto."""
        return (self.x2 - self.x1) * (self.y2 - self.y1)

    @property
    def centro(self) -> tuple[float, float]:
        """Centro (x, y); el rastreador lo usa para el historial y para detectar cruces de la
        línea.
        """
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)


@dataclass(frozen=True)
class Deteccion:
    """Una detección: clase, confianza en [0, 1] y caja."""
    clase: str
    confianza: float
    caja: Caja

    def a_dict(self) -> dict:
        """Diccionario para el JSON, con la confianza redondeada a 4 decimales para que el
        archivo sea legible y estable.
        """
        d = asdict(self)
        d["confianza"] = round(self.confianza, 4)
        return d


class Detector(Protocol):
    """Interfaz común de los detectores: el real (YOLO) y el falso (por colores).

    El resto del programa (CLI, postproceso, dibujo) solo conoce esta interfaz, así que
    se prueba entero con el detector falso, sin descargar pesos ni tener GPU.
    """

    nombre: str

    def detectar(self, imagen: Image.Image) -> list[Deteccion]:
        """Devuelve las detecciones de la imagen (coordenadas en píxeles, x2/y2 exclusivos)."""
        ...


class DetectorYOLO:
    """Envoltura de ultralytics. ``pesos`` puede ser ``yolov8n.pt``, ``yolo11n.pt`` o un modelo propio.

    Ojo: la primera vez ultralytics **descarga** los pesos de Internet si no
    existen localmente (por eso nunca se usa en los tests).
    """

    nombre = "yolo"

    def __init__(self, pesos: str = "yolo11n.pt", confianza: float = 0.25, dispositivo: str | None = None) -> None:
        """Carga el modelo de ultralytics (que descarga los pesos la primera vez). Si
        ultralytics no está instalado, da un error que explica cómo instalarlo o
        usar --falso.
        """
        try:
            from ultralytics import YOLO
        except ImportError as e:
            raise RuntimeError("falta ultralytics: pip install -e '.[yolo]' (o usá --falso)") from e
        self._modelo = YOLO(pesos)
        self.confianza, self.dispositivo = confianza, dispositivo

    def detectar(self, imagen: Image.Image) -> list[Deteccion]:
        """Corre la predicción y convierte las cajas xyxy, confianzas e índices de clase de
        ultralytics a nuestras Deteccion con el nombre de la clase.
        """
        res = self._modelo.predict(imagen.convert("RGB"), conf=self.confianza, device=self.dispositivo, verbose=False)[0]
        nombres = res.names
        salida = []
        for xyxy, conf, cls in zip(res.boxes.xyxy.tolist(), res.boxes.conf.tolist(), res.boxes.cls.tolist()):
            salida.append(Deteccion(nombres[int(cls)], float(conf), Caja(*map(float, xyxy))))
        return salida


COLORES_FALSOS: dict[str, tuple[int, int, int]] = {"persona": (255, 0, 0), "auto": (0, 0, 255), "perro": (0, 255, 0)}


class DetectorFalso:
    """Detecta blobs de colores puros (tolerancia configurable). La confianza crece con el área y la "solidez"."""

    nombre = "falso"

    def __init__(self, tolerancia: int = 40, area_minima: int = 25) -> None:
        """``tolerancia``: distancia máxima por canal al color de la clase. ``area_minima``: en
        píxeles; las manchas más chicas son ruido.
        """
        self.tolerancia, self.area_minima = tolerancia, area_minima

    def detectar(self, imagen: Image.Image) -> list[Deteccion]:
        """Por cada clase arma una máscara de los píxeles cercanos a su color y busca
        componentes conexas. La confianza crece con la 'solidez' (área / área de su
        caja: 1 para un rectángulo, ~0.785 = π/4 para una elipse) y un poco con el
        tamaño, con tope en 0.99. Ordena por confianza descendente y posición, así
        el resultado es determinista.
        """
        px = np.asarray(imagen.convert("RGB"), dtype=np.int16)
        salida: list[Deteccion] = []
        for clase, color in COLORES_FALSOS.items():
            mascara = np.all(np.abs(px - np.array(color)) <= self.tolerancia, axis=2)
            for (y1, x1, y2, x2), area in _componentes(mascara):
                if area < self.area_minima:
                    continue
                solidez = area / ((x2 - x1 + 1) * (y2 - y1 + 1))
                conf = min(0.99, 0.5 + 0.4 * solidez + min(0.09, area / 100_000))
                salida.append(Deteccion(clase, conf, Caja(x1, y1, x2 + 1, y2 + 1)))
        return sorted(salida, key=lambda d: (-d.confianza, d.caja.x1, d.caja.y1))


def _componentes(mascara: np.ndarray) -> list[tuple[tuple[int, int, int, int], int]]:
    """Componentes 4-conexas por BFS: devuelve (bbox (y1,x1,y2,x2), área) de cada una."""
    alto, ancho = mascara.shape
    visto = np.zeros_like(mascara, dtype=bool)
    out = []
    for y, x in zip(*np.nonzero(mascara)):
        if visto[y, x]:
            continue
        cola = deque([(y, x)])
        visto[y, x] = True
        y1 = y2 = y
        x1 = x2 = x
        area = 0
        while cola:
            cy, cx = cola.popleft()
            area += 1
            y1, y2, x1, x2 = min(y1, cy), max(y2, cy), min(x1, cx), max(x2, cx)
            for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                if 0 <= ny < alto and 0 <= nx < ancho and mascara[ny, nx] and not visto[ny, nx]:
                    visto[ny, nx] = True
                    cola.append((ny, nx))
        out.append(((int(y1), int(x1), int(y2), int(x2)), area))
    return out


def crear_detector(falso: bool = False, **kw) -> Detector:
    """Fábrica: el falso o el YOLO (con los argumentos que correspondan)."""
    return DetectorFalso() if falso else DetectorYOLO(**kw)
