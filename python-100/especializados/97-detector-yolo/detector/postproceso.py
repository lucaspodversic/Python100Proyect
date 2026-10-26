"""Post-procesado independiente del backend: IoU, NMS, filtros y conteos."""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from .modelo import Caja, Deteccion


def iou(a: Caja, b: Caja) -> float:
    """Intersección sobre unión, en [0, 1]."""
    ix = max(0.0, min(a.x2, b.x2) - max(a.x1, b.x1))
    iy = max(0.0, min(a.y2, b.y2) - max(a.y1, b.y1))
    inter = ix * iy
    union = a.area + b.area - inter
    return inter / union if union > 0 else 0.0


def nms(dets: Iterable[Deteccion], umbral: float = 0.5, por_clase: bool = True) -> list[Deteccion]:
    """Non-Maximum Suppression voraz: se queda con la de mayor confianza y descarta
    las que se solapan con ella más que ``umbral`` (solo dentro de la misma clase si ``por_clase``)."""
    pendientes = sorted(dets, key=lambda d: d.confianza, reverse=True)
    elegidas: list[Deteccion] = []
    for d in pendientes:
        if all((por_clase and e.clase != d.clase) or iou(e.caja, d.caja) <= umbral for e in elegidas):
            elegidas.append(d)
    return elegidas


def filtrar(dets: Iterable[Deteccion], confianza: float = 0.0, clases: set[str] | None = None,
            area_minima: float = 0.0) -> list[Deteccion]:
    """Se queda con las detecciones de confianza >= umbral, de las clases pedidas (vacío =
    todas) y de área >= mínima.
    """
    return [d for d in dets if d.confianza >= confianza and (not clases or d.clase in clases) and d.caja.area >= area_minima]


def contar(dets: Iterable[Deteccion]) -> dict[str, int]:
    """Conteo por clase, ordenado alfabéticamente para que el JSON sea estable."""
    return dict(sorted(Counter(d.clase for d in dets).items()))
