"""Elección del umbral de decisión.

Con 1 % de fraude, el umbral 0.5 por defecto casi nunca es el adecuado. Se
ofrecen dos criterios de negocio:

1. **Mínimo costo esperado**: cada fraude no detectado (FN) cuesta su monto
   (contracargo) y cada alerta (TP o FP) cuesta una revisión manual; un FP
   además molesta al cliente (costo de fricción).
2. **Recall mínimo**: "quiero atrapar al menos el 80 % del fraude" → el umbral
   más alto que lo cumple (maximiza precisión bajo esa restricción).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Costos:
    revision: float = 5.0  # costo operativo de revisar una alerta
    friccion_fp: float = 10.0  # cliente legítimo bloqueado / molesto
    # El costo de un fraude no detectado es su propio monto.


def costo_total(y: np.ndarray, prob: np.ndarray, montos: np.ndarray, umbral: float, c: Costos = Costos()) -> float:
    y, prob, montos = np.asarray(y), np.asarray(prob), np.asarray(montos, float)
    # Costo = montos de los FN + revisión de cada alerta (TP o FP) + fricción extra de cada FP.
    alerta = prob >= umbral
    fn = (y == 1) & ~alerta
    fp = (y == 0) & alerta
    return float(montos[fn].sum() + alerta.sum() * c.revision + fp.sum() * c.friccion_fp)


def umbral_minimo_costo(y: np.ndarray, prob: np.ndarray, montos: np.ndarray, c: Costos = Costos(),
                        grilla: np.ndarray | None = None) -> tuple[float, float]:
    """Devuelve (umbral, costo) que minimiza el costo total sobre una grilla de umbrales."""
    # 400 umbrales en (0, 1) más el 0.5 exacto, para que el óptimo nunca sea peor que el umbral por defecto.
    grilla = np.unique(np.concatenate([np.linspace(0.001, 0.999, 400), [0.5]])) if grilla is None else grilla
    costos = np.array([costo_total(y, prob, montos, u, c) for u in grilla])
    # Ante empates argmin devuelve el primero (el umbral más bajo).
    i = int(np.argmin(costos))
    return float(grilla[i]), float(costos[i])


def umbral_para_recall(y: np.ndarray, prob: np.ndarray, recall_min: float) -> float:
    """Mayor umbral con recall ≥ recall_min (las predicciones con prob ≥ umbral son alertas)."""
    y, prob = np.asarray(y), np.asarray(prob)
    # Probabilidades de los fraudes reales, de mayor a menor: el k-ésimo es el umbral que atrapa k fraudes.
    positivos = np.sort(prob[y == 1])[::-1]
    if len(positivos) == 0:
        raise ValueError("no hay positivos para calcular recall")
    k = int(np.ceil(recall_min * len(positivos)))  # cantidad de fraudes que hay que atrapar
    # max(k, 1) evita el índice −1 si recall_min = 0.
    return float(positivos[max(k, 1) - 1])
