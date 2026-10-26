"""Backtesting con origen móvil y métricas de error."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .modelos import pronosticar


def metricas(real: np.ndarray, pred: np.ndarray, entrenamiento: np.ndarray, periodo: int = 12) -> dict[str, float]:
    """MAE, MAPE (%) y MASE (MAE relativo al naive estacional in-sample: < 1 = mejor que el naive)."""
    real, pred = np.asarray(real, float), np.asarray(pred, float)
    # MAE en unidades de ventas; MAPE en % (asume valores reales ≠ 0).
    mae = float(np.mean(np.abs(real - pred)))
    entrenamiento = np.asarray(entrenamiento, float)
    # Ojo: np.diff(x, n) es la diferencia de orden n, NO con rezago n; por eso se resta a mano.
    # Escala de MASE = MAE del naive estacional dentro del entrenamiento; NaN si no hay ni un ciclo.
    escala = (float(np.mean(np.abs(entrenamiento[periodo:] - entrenamiento[:-periodo])))
              if len(entrenamiento) > periodo else np.nan)
    return {"mae": mae, "mape": float(np.mean(np.abs((real - pred) / real)) * 100), "mase": mae / escala}


def backtest(serie: pd.Series, modelos: list[str], horizonte: int = 6, origenes: int = 3, periodo: int = 12) -> pd.DataFrame:
    """Para cada origen (los últimos `origenes` cortes, separados por `horizonte`) entrena con el
    pasado y evalúa en los `horizonte` meses siguientes. Devuelve métricas promediadas por modelo."""
    filas = []
    # Orígenes del más antiguo al más reciente: p. ej. con 72 meses, h=6 y 3 orígenes → cortes en 54, 60 y 66.
    for i in range(origenes, 0, -1):
        corte = len(serie) - i * horizonte
        # Sólo se entrena con el pasado del corte: nada del futuro se filtra al modelo.
        train, test = serie.iloc[:corte], serie.iloc[corte:corte + horizonte]
        for m in modelos:
            p = pronosticar(train, len(test), modelo=m, periodo=periodo)
            met = metricas(test.to_numpy(), p.media.to_numpy(), train.to_numpy(), periodo)
            # Cobertura empírica: fracción de reales dentro de la banda del 80% (idealmente ≈ 0.8).
            cubre = float(((test.to_numpy() >= p.inferior.to_numpy()) & (test.to_numpy() <= p.superior.to_numpy())).mean())
            filas.append({"modelo": m, "usado": p.modelo, "origen": str(serie.index[corte - 1].date()), **met,
                          "cobertura_80": cubre})
    # Promedio por modelo sobre todos los orígenes; el mejor (menor MAE) queda primero.
    return pd.DataFrame(filas).groupby("modelo")[["mae", "mape", "mase", "cobertura_80"]].mean().sort_values("mae")
