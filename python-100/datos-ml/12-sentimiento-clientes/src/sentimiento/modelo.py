"""Clasificador TF-IDF (palabras + n-gramas de caracteres) + regresión logística.

Por qué esta combinación:
- n-gramas de **palabras** (1-2) capturan expresiones ("no_gusto", "muy buena");
- n-gramas de **caracteres** (3-5, ``char_wb``) toleran errores de tipeo y
  variantes ("buenisimo", "buenisima", "buenisimooo");
- la regresión logística da probabilidades calibradas razonablemente y
  coeficientes interpretables (qué palabras empujan a cada clase).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.pipeline import FeatureUnion, Pipeline

from .corpus import ETIQUETAS
from .texto import normalizar


def construir_pipeline(c: float = 4.0) -> Pipeline:
    rasgos = FeatureUnion([
        # sublinear_tf: usa 1 + log(tf), así repetir una palabra 5 veces no pesa 5 veces más.
        # min_df=1 en palabras (corpus chico); min_df=2 en caracteres para descartar n-gramas únicos (ruido).
        ("palabras", TfidfVectorizer(preprocessor=normalizar, ngram_range=(1, 2), min_df=1, sublinear_tf=True)),
        ("caracteres", TfidfVectorizer(preprocessor=normalizar, analyzer="char_wb", ngram_range=(3, 5),
                                       min_df=2, sublinear_tf=True)),
    ])
    return Pipeline([("rasgos", rasgos),
                     # C=4 (regularización suave): con pocos datos y muchos rasgos rinde mejor que el C=1 por defecto.
                     # class_weight="balanced" compensa si un CSV real tiene clases desbalanceadas.
                     ("clf", LogisticRegression(C=c, max_iter=2000, class_weight="balanced"))])


@dataclass
class ClasificadorSentimiento:
    pipeline: Pipeline = field(default_factory=construir_pipeline)
    # Con 0.0 (por defecto) nunca se fuerza neutro; subirlo (p. ej. 0.6) marca como neutro los casos dudosos.
    umbral_neutro: float = 0.0  # si la confianza máxima < umbral, se devuelve "neutro"

    def entrenar(self, textos: Iterable[str], etiquetas: Iterable[str]) -> "ClasificadorSentimiento":
        self.pipeline.fit(list(textos), list(etiquetas))
        return self

    def predecir(self, textos: list[str]) -> list[str]:
        proba = self.pipeline.predict_proba(textos)
        clases = self.pipeline.classes_
        salida = []
        for fila in proba:
            # Clase más probable; si su probabilidad no alcanza el umbral, se responde "neutro".
            i = int(np.argmax(fila))
            salida.append(str(clases[i]) if fila[i] >= self.umbral_neutro else "neutro")
        return salida

    def predecir_con_confianza(self, textos: list[str]) -> list[tuple[str, float]]:
        proba = self.pipeline.predict_proba(textos)
        return [(e, float(p.max())) for e, p in zip(self.predecir(textos), proba)]

    def evaluar(self, df: pd.DataFrame) -> dict[str, object]:
        pred = self.predecir(df["texto"].tolist())
        return {"accuracy": accuracy_score(df["etiqueta"], pred),
                "f1_macro": f1_score(df["etiqueta"], pred, average="macro"),
                # labels fijo: filas/columnas siempre en el orden positivo, negativo, neutro.
                "matriz": confusion_matrix(df["etiqueta"], pred, labels=list(ETIQUETAS)),
                "reporte": classification_report(df["etiqueta"], pred, zero_division=0)}

    def palabras_clave(self, k: int = 8) -> dict[str, list[str]]:
        """Rasgos de palabra con mayor peso positivo para cada clase (explicabilidad)."""
        # FeatureUnion concatena columnas [palabras | caracteres]; los primeros n coeficientes son de palabras.
        vec: TfidfVectorizer = self.pipeline.named_steps["rasgos"].transformer_list[0][1]
        n = len(vec.vocabulary_)
        nombres = vec.get_feature_names_out()
        coef = self.pipeline.named_steps["clf"].coef_[:, :n]  # el bloque de palabras va primero
        # argsort ascendente invertido → índices de mayor a menor peso; se toman los k primeros.
        return {str(c): [str(nombres[i]) for i in np.argsort(coef[j])[::-1][:k]]
                for j, c in enumerate(self.pipeline.classes_)}

    def guardar(self, ruta: Path) -> None:
        # Se serializa el objeto completo (pipeline + umbral). La función normalizar se guarda por
        # referencia: hace falta tener el paquete instalado para cargarlo.
        joblib.dump(self, ruta)

    @staticmethod
    def cargar(ruta: Path) -> "ClasificadorSentimiento":
        return joblib.load(ruta)  # ⚠ sólo archivos de confianza
