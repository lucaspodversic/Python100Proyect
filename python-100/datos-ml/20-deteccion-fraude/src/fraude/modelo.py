"""Modelos y evaluación para clases muy desbalanceadas.

- **Métrica principal: PR-AUC (average precision)**. La exactitud engaña: un
  modelo que dice "nunca es fraude" tiene 99 % de exactitud y no sirve.
- Desbalance tratado con **pesos de clase** (``class_weight="balanced"`` /
  ``sample_weight``) en vez de sobremuestreo, para no inventar datos ni
  agregar dependencias (imbalanced-learn).
- El umbral se elige en un conjunto de **validación** separado del test, para
  que el costo reportado en test sea honesto.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, confusion_matrix, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler
from sklearn.utils.class_weight import compute_sample_weight

from .datos import ATRIBUTOS, BINARIOS, NUMERICOS
from .umbral import Costos, costo_total, umbral_minimo_costo, umbral_para_recall


def _log_montos(x: pd.DataFrame) -> pd.DataFrame:
    x = x.copy()
    for c in ("monto", "distancia_km", "ratio_monto_promedio"):
        # log1p comprime colas largas (montos, distancias) y soporta 0; útil para la regresión logística.
        x[c] = np.log1p(x[c])
    return x


def construir(tipo: str, semilla: int = 0) -> Pipeline:
    if tipo == "logistica":
        # Logística: log + estandarización en numéricos, binarios tal cual, one-hot en rubro.
        prep = ColumnTransformer([("num", Pipeline([("log", FunctionTransformer(_log_montos)), ("esc", StandardScaler())]),
                                   NUMERICOS), ("bin", "passthrough", BINARIOS),
                                  ("cat", OneHotEncoder(handle_unknown="ignore"), ["rubro"])])
        # La transformación log se aplica sobre el DataFrame completo de numéricos.
        return Pipeline([("prep", prep), ("clf", LogisticRegression(class_weight="balanced", max_iter=2000))])
    if tipo == "boosting":
        # Árboles: no necesitan escalar ni log (sólo importan los órdenes); sparse_output=False porque HistGB espera matriz densa.
        prep = ColumnTransformer([("num", "passthrough", NUMERICOS + BINARIOS),
                                  ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), ["rubro"])])
        # Hiperparámetros moderados (hojas chicas, l2) para no sobreajustar a los pocos fraudes.
        clf = HistGradientBoostingClassifier(max_iter=250, learning_rate=0.06, max_leaf_nodes=15,
                                             l2_regularization=1.0, random_state=semilla)
        return Pipeline([("prep", prep), ("clf", clf)])
    raise ValueError(f"tipo desconocido: {tipo}")


@dataclass
class DetectorFraude:
    tipo: str = "boosting"
    costos: Costos = field(default_factory=Costos)
    semilla: int = 0
    umbral: float = 0.5
    modelo: Pipeline | None = None

    def entrenar(self, train: pd.DataFrame, validacion: pd.DataFrame, criterio: str = "costo",
                 recall_min: float = 0.8) -> "DetectorFraude":
        self.modelo = construir(self.tipo, self.semilla)
        kw = {}
        if self.tipo == "boosting":  # HistGB no tiene class_weight en todas las versiones: usar sample_weight
            # "balanced": cada fraude pesa ~99 veces más que una legítima; "clf__" dirige el parámetro al paso clf.
            kw["clf__sample_weight"] = compute_sample_weight("balanced", train["fraude"])
        self.modelo.fit(train[ATRIBUTOS], train["fraude"], **kw)
        # El umbral se ajusta con probabilidades de validación (no de train, que serían optimistas).
        p = self.probabilidad(validacion)
        if criterio == "costo":
            self.umbral, _ = umbral_minimo_costo(validacion["fraude"], p, validacion["monto"], self.costos)
        elif criterio == "recall":
            self.umbral = umbral_para_recall(validacion["fraude"].to_numpy(), p, recall_min)
        else:
            raise ValueError("criterio debe ser 'costo' o 'recall'")
        return self

    def probabilidad(self, df: pd.DataFrame) -> np.ndarray:
        if self.modelo is None:
            raise RuntimeError("modelo no entrenado")
        # Columna 1 = probabilidad de la clase fraude; se seleccionan sólo los atributos (ignora columnas extra).
        return self.modelo.predict_proba(df[ATRIBUTOS])[:, 1]

    def predecir(self, df: pd.DataFrame) -> np.ndarray:
        return (self.probabilidad(df) >= self.umbral).astype(int)

    def evaluar(self, df: pd.DataFrame, umbral: float | None = None) -> dict[str, float]:
        y, p = df["fraude"].to_numpy(), self.probabilidad(df)
        u = self.umbral if umbral is None else umbral
        pred = (p >= u).astype(int)
        # labels=[0, 1] garantiza una matriz 2×2 aunque no haya predicciones positivas.
        tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
        return {"pr_auc": float(average_precision_score(y, p)), "roc_auc": float(roc_auc_score(y, p)),
                "umbral": float(u), "precision": float(precision_score(y, pred, zero_division=0)),
                "recall": float(recall_score(y, pred)), "tp": int(tp), "fp": int(fp), "fn": int(fn), "tn": int(tn),
                "costo": costo_total(y, p, df["monto"].to_numpy(), u, self.costos)}

    def guardar(self, ruta: Path | str) -> None:
        joblib.dump(self, ruta)

    @staticmethod
    def cargar(ruta: Path | str) -> "DetectorFraude":
        # ⚠️ joblib usa pickle: cargar sólo archivos propios y de confianza.
        return joblib.load(ruta)


def dividir(df: pd.DataFrame, semilla: int = 0) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """60 / 20 / 20 estratificado (train / validación para el umbral / test)."""
    # stratify mantiene ~1% de fraude en cada parte; sin eso val o test podrían quedar casi sin fraudes.
    train, resto = train_test_split(df, test_size=0.4, stratify=df["fraude"], random_state=semilla)
    val, test = train_test_split(resto, test_size=0.5, stratify=resto["fraude"], random_state=semilla)
    return train, val, test


def comparar(df: pd.DataFrame, semilla: int = 0) -> pd.DataFrame:
    """Tabla comparativa en test: baseline 'nunca fraude', y cada modelo con umbral 0.5 vs. optimizado."""
    train, val, test = dividir(df, semilla)
    y = test["fraude"].to_numpy()
    # Baseline: nunca alerta. Exactitud ≈ 99%, PR-AUC = prevalencia, costo = todos los montos fraudulentos.
    filas = [{"modelo": "nunca_fraude", "exactitud": float((y == 0).mean()), "pr_auc": float(y.mean()), "recall": 0.0,
              "precision": 0.0, "costo": float(test.loc[test["fraude"] == 1, "monto"].sum())}]
    for tipo in ("logistica", "boosting"):
        d = DetectorFraude(tipo, semilla=semilla).entrenar(train, val)
        # Mismo modelo evaluado con el umbral por defecto y con el umbral de mínimo costo.
        for nombre, u in ((f"{tipo}@0.5", 0.5), (f"{tipo}@costo", d.umbral)):
            r = d.evaluar(test, u)
            filas.append({"modelo": nombre, "exactitud": (r["tp"] + r["tn"]) / len(test), "pr_auc": r["pr_auc"],
                          "recall": r["recall"], "precision": r["precision"], "costo": r["costo"], "umbral": u})
    return pd.DataFrame(filas).set_index("modelo")
