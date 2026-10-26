"""Pipeline de entrenamiento, evaluación, persistencia y predicción.

``Pipeline`` = preprocesado + modelo en un solo objeto: evita *data leakage*
(el escalado se ajusta sólo con el train de cada fold) y se serializa entero.
El modelo predice ``log(precio)``: los precios son asimétricos y el error
relativo es más estable en escala log (``TransformedTargetRegressor``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.base import RegressorMixin
from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, mean_squared_error, r2_score
from sklearn.model_selection import KFold, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .datos import CATEGORICAS, COLUMNAS, NUMERICAS, OBJETIVO

# Fábricas (lambdas) en vez de instancias: cada pipeline recibe un modelo nuevo sin estado compartido.
# random_state fijo → resultados reproducibles; n_jobs=1 evita procesos extra en tests.
MODELOS: dict[str, Any] = {
    "ridge": lambda: Ridge(alpha=1.0),
    "bosque": lambda: RandomForestRegressor(n_estimators=150, min_samples_leaf=2, random_state=0, n_jobs=1),
    "gbr": lambda: GradientBoostingRegressor(n_estimators=300, learning_rate=0.05, max_depth=3, random_state=0),
}


def construir_pipeline(nombre: str = "gbr") -> Pipeline:
    pre = ColumnTransformer([
        # Escalado: imprescindible para Ridge (penaliza coeficientes) e inocuo para los árboles.
        ("num", StandardScaler(), NUMERICAS),
        # handle_unknown="ignore": un barrio nuevo no rompe la predicción (queda todo en 0).
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAS),
    ])
    # El modelo aprende log(precio) y la predicción se devuelve con exp → precio en USD.
    reg: RegressorMixin = TransformedTargetRegressor(regressor=MODELOS[nombre](), func=np.log, inverse_func=np.exp)
    return Pipeline([("pre", pre), ("modelo", reg)])


def comparar_modelos(df: pd.DataFrame, folds: int = 5) -> dict[str, float]:
    """R² medio en validación cruzada para cada modelo candidato."""
    # shuffle=True: el CSV podría venir ordenado (por barrio o precio) y los folds quedarían sesgados.
    cv = KFold(folds, shuffle=True, random_state=0)
    return {n: float(cross_val_score(construir_pipeline(n), df[COLUMNAS], df[OBJETIVO], cv=cv, scoring="r2").mean())
            for n in MODELOS}


@dataclass
class Predictor:
    nombre: str = "gbr"
    pipeline: Pipeline | None = None
    metricas: dict[str, float] = field(default_factory=dict)

    def entrenar(self, df: pd.DataFrame, test_size: float = 0.2) -> dict[str, float]:
        # Validación temprana con mensaje claro, en lugar de un KeyError de pandas.
        faltan = set(COLUMNAS + [OBJETIVO]) - set(df.columns)
        if faltan:
            raise ValueError(f"Faltan columnas: {sorted(faltan)}")
        # Filas incompletas se descartan (estrategia simple; una alternativa sería imputar en el pipeline).
        df = df.dropna(subset=COLUMNAS + [OBJETIVO])
        # 80/20 con semilla fija: las métricas se calculan sobre datos que el modelo no vio.
        xtr, xte, ytr, yte = train_test_split(df[COLUMNAS], df[OBJETIVO], test_size=test_size, random_state=0)
        self.pipeline = construir_pipeline(self.nombre).fit(xtr, ytr)
        pred = self.pipeline.predict(xte)
        self.metricas = {"mae": float(mean_absolute_error(yte, pred)),
                         # RMSE = raíz del MSE, calculado a mano para ser compatible con distintas versiones de sklearn.
                         "rmse": float(np.sqrt(mean_squared_error(yte, pred))),
                         "mape": float(mean_absolute_percentage_error(yte, pred)),
                         "r2": float(r2_score(yte, pred))}
        return self.metricas

    def predecir(self, casas: list[dict[str, Any]] | pd.DataFrame) -> np.ndarray:
        if self.pipeline is None:
            raise RuntimeError("Modelo no entrenado")
        # Acepta lista de dicts (uso desde la CLI o una API) o un DataFrame.
        df = pd.DataFrame(casas) if not isinstance(casas, pd.DataFrame) else casas
        faltan = set(COLUMNAS) - set(df.columns)
        if faltan:
            raise ValueError(f"Faltan columnas: {sorted(faltan)}")
        # Se seleccionan las columnas en el orden de entrenamiento; columnas extra se ignoran.
        return np.asarray(self.pipeline.predict(df[COLUMNAS]))

    def importancias(self) -> pd.Series:
        """Importancia de variables (sólo modelos de árboles)."""
        assert self.pipeline is not None
        # regressor_ (con guion bajo) es el modelo ya ajustado dentro del TransformedTargetRegressor.
        reg = self.pipeline.named_steps["modelo"].regressor_
        # Nombres tras el ColumnTransformer: "num__m2", "cat__barrio_Costa", etc.
        nombres = self.pipeline.named_steps["pre"].get_feature_names_out()
        return pd.Series(reg.feature_importances_, index=nombres).sort_values(ascending=False)

    def guardar(self, ruta: Path) -> None:
        # Se guardan nombre y métricas junto al pipeline para saber qué modelo es al cargarlo.
        joblib.dump({"nombre": self.nombre, "pipeline": self.pipeline, "metricas": self.metricas}, ruta)

    @classmethod
    def cargar(cls, ruta: Path) -> "Predictor":
        # ⚠ joblib/pickle ejecuta código al cargar: sólo abrir modelos propios.
        d = joblib.load(ruta)
        return cls(d["nombre"], d["pipeline"], d["metricas"])
