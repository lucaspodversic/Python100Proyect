"""Modelo: Gradient Boosting para el valor esperado + dos modelos de cuantiles (p10/p90).

Prometerle al cliente "llega en 32 min" sirve poco; "entre 27 y 40 min" sirve
más. Por eso además del punto se entrenan regresores con pérdida *quantile*.

Ingeniería de atributos:
- La hora se codifica cíclicamente (seno/coseno) y además con un indicador de
  hora pico, para que 23 hs y 0 hs queden "cerca".
- El fin de semana se codifica como binario.
- Las categóricas (clima, vehículo) se pasan por One-Hot.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder

from .datos import COLUMNAS, OBJETIVO


def _atributos(df: pd.DataFrame) -> pd.DataFrame:
    x = df[COLUMNAS].copy()
    # Hora → ángulo en la circunferencia: sin/cos hacen que 23 hs y 0 hs queden contiguas.
    ang = 2 * np.pi * x["hora"] / 24
    x["hora_sin"], x["hora_cos"] = np.sin(ang), np.cos(ang)
    x["finde"] = (x["dia_semana"] >= 5).astype(int)
    # Indicador explícito de horas pico: ayuda a los árboles a separar esa región en un solo corte.
    x["pico"] = x["hora"].isin([12, 13, 14, 20, 21, 22]).astype(int)
    return x


def _pipeline(regresor: object) -> Pipeline:
    # remainder="passthrough": las numéricas (y las derivadas) pasan sin cambios; los árboles no necesitan escalado.
    cols = ColumnTransformer([("cat", OneHotEncoder(handle_unknown="ignore"), ["clima", "vehiculo"])],
                             remainder="passthrough")
    # La ingeniería de atributos va DENTRO del pipeline: se aplica igual al entrenar, predecir y tras cargar.
    return Pipeline([("fe", FunctionTransformer(_atributos)), ("prep", cols), ("reg", regresor)])


@dataclass
class Prediccion:
    estimado_min: float
    minimo_min: float  # p10
    maximo_min: float  # p90

    def texto(self) -> str:
        return f"Llega en ~{self.estimado_min:.0f} min (entre {self.minimo_min:.0f} y {self.maximo_min:.0f})"


class PredictorEntregas:
    def __init__(self, semilla: int = 0, n_estimadores: int = 300) -> None:
        # Árboles poco profundos + learning_rate bajo + subsample 0.8 (boosting estocástico): menos sobreajuste.
        base = dict(n_estimators=n_estimadores, max_depth=3, learning_rate=0.05, subsample=0.8, random_state=semilla)
        # Pérdida "huber": robusta a la cola pesada del ruido (pedidos que se demoran mucho).
        self.medio = _pipeline(GradientBoostingRegressor(loss="huber", **base))
        # Pérdida cuantílica: con alpha=0.10 el modelo aprende el valor por debajo del cual cae el 10% de los casos.
        self.p10 = _pipeline(GradientBoostingRegressor(loss="quantile", alpha=0.10, **base))
        self.p90 = _pipeline(GradientBoostingRegressor(loss="quantile", alpha=0.90, **base))

    def entrenar(self, df: pd.DataFrame) -> "PredictorEntregas":
        x, y = df[COLUMNAS], df[OBJETIVO]
        for m in (self.medio, self.p10, self.p90):
            m.fit(x, y)
        return self

    def predecir(self, df: pd.DataFrame) -> pd.DataFrame:
        x = df[COLUMNAS]
        medio, bajo, alto = self.medio.predict(x), self.p10.predict(x), self.p90.predict(x)
        # Los cuantiles se entrenan por separado y pueden "cruzarse": se ordenan.
        bajo, alto = np.minimum(bajo, medio), np.maximum(alto, medio)
        return pd.DataFrame({"estimado": medio, "p10": bajo, "p90": alto}, index=df.index)

    def predecir_uno(self, **pedido: object) -> Prediccion:
        # Un solo pedido como DataFrame de una fila, para reutilizar predecir().
        fila = self.predecir(pd.DataFrame([pedido])).iloc[0]
        return Prediccion(float(fila["estimado"]), float(fila["p10"]), float(fila["p90"]))

    def importancias(self) -> pd.Series:
        nombres = self.medio.named_steps["prep"].get_feature_names_out()
        imp = self.medio.named_steps["reg"].feature_importances_
        # Se quita el prefijo del ColumnTransformer ("remainder__distancia_km" → "distancia_km").
        limpio = [n.split("__", 1)[1] for n in nombres]
        return pd.Series(imp, index=limpio).sort_values(ascending=False)

    def guardar(self, ruta: Path | str) -> None:
        joblib.dump(self, ruta)

    @staticmethod
    def cargar(ruta: Path | str) -> "PredictorEntregas":
        # ⚠️ joblib usa pickle: cargar sólo archivos propios y de confianza.
        return joblib.load(ruta)


def evaluar(df: pd.DataFrame, semilla: int = 0) -> dict[str, float]:
    """MAE del modelo frente a dos baselines (media y regresión lineal) + cobertura del intervalo."""
    # 75/25 con semilla: todos los modelos se comparan sobre el mismo test.
    tr, te = train_test_split(df, test_size=0.25, random_state=semilla)
    p = PredictorEntregas(semilla).entrenar(tr)
    pred = p.predecir(te)
    lineal = _pipeline(LinearRegression()).fit(tr[COLUMNAS], tr[OBJETIVO])
    y = te[OBJETIVO]
    return {
        # Baselines: predecir siempre la media y una regresión lineal con los mismos atributos.
        "mae_media": float(mean_absolute_error(y, np.full(len(y), tr[OBJETIVO].mean()))),
        "mae_lineal": float(mean_absolute_error(y, lineal.predict(te[COLUMNAS]))),
        "mae_gbr": float(mean_absolute_error(y, pred["estimado"])),
        # Proporción de entregas reales dentro del intervalo; lo ideal sería ~80%.
        "cobertura_p10_p90": float(((y >= pred["p10"]) & (y <= pred["p90"])).mean()),
        "ancho_medio_intervalo": float((pred["p90"] - pred["p10"]).mean()),
    }
