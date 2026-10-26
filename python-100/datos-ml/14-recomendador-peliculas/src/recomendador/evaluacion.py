"""Métricas: RMSE (error de la nota) y precision@k (calidad del ranking)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .datos import Calificaciones


def rmse(pred: np.ndarray, c_train: Calificaciones, test: pd.DataFrame) -> float:
    # Índices (fila, columna) de cada calificación de test para leer la predicción con indexación avanzada.
    u = np.array([c_train.idx_usuario(x) for x in test["usuario"]])
    i = np.array([c_train.idx_pelicula(x) for x in test["pelicula"]])
    return float(np.sqrt(((pred[u, i] - test["nota"].to_numpy()) ** 2).mean()))


def precision_at_k(pred: np.ndarray, c_train: Calificaciones, test: pd.DataFrame, k: int = 5,
                   relevante: float = 4.0) -> float:
    """Proporción de los top-k recomendados (entre las del test de cada usuario) que le gustaron (≥ 4)."""
    valores = []
    for usuario, grupo in test.groupby("usuario"):
        # Usuarios con menos de k notas en test no permiten armar un top-k: se omiten.
        if len(grupo) < k:
            continue
        u = c_train.idx_usuario(str(usuario))
        idx = [c_train.idx_pelicula(p) for p in grupo["pelicula"]]
        # Se ordenan sólo las películas de test del usuario (cuya nota real conocemos) por nota predicha.
        top = np.argsort(-pred[u, idx])[:k]
        valores.append(float((grupo["nota"].to_numpy()[top] >= relevante).mean()))
    # NaN si ningún usuario califica: mejor que un 0 engañoso.
    return float(np.mean(valores)) if valores else float("nan")
