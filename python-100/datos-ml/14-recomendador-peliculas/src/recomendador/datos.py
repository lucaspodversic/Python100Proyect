"""Datos: matriz de calificaciones y generador sintético con gustos latentes.

Formato "largo" (una fila por calificación: usuario, pelicula, nota), igual que
MovieLens (``ratings.csv``: userId, movieId, rating). ``Calificaciones``
lo convierte a matriz densa usuarios × películas con ``NaN`` en lo no visto.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

GENEROS = ["Acción", "Comedia", "Drama", "Terror", "Animación"]


@dataclass
class Calificaciones:
    matriz: np.ndarray  # (usuarios, películas), NaN = sin calificar
    usuarios: list[str]
    peliculas: list[str]

    @classmethod
    def desde_df(cls, df: pd.DataFrame, usuarios: list[str] | None = None,
                 peliculas: list[str] | None = None) -> "Calificaciones":
        """Pivota un DataFrame largo. Se pueden fijar los ejes para alinear train/test."""
        # Ejes ordenados alfabéticamente si no se fijan: resultado determinista.
        usuarios = usuarios or sorted(df["usuario"].unique())
        peliculas = peliculas or sorted(df["pelicula"].unique())
        # aggfunc="mean": si un usuario calificó dos veces la misma película se promedia.
        m = df.pivot_table(index="usuario", columns="pelicula", values="nota", aggfunc="mean")
        # reindex agrega filas/columnas faltantes con NaN (usuarios o películas sin notas en este split).
        m = m.reindex(index=usuarios, columns=peliculas)
        return cls(m.to_numpy(dtype=float), list(usuarios), list(peliculas))

    def idx_usuario(self, u: str) -> int:
        # Búsqueda lineal: suficiente para cientos de elementos; con millones convendría un dict.
        return self.usuarios.index(u)

    def idx_pelicula(self, p: str) -> int:
        return self.peliculas.index(p)


def generar_calificaciones(n_usuarios: int = 200, por_genero: int = 10, densidad: float = 0.35,
                           semilla: int = 0) -> pd.DataFrame:
    """Cada usuario tiene afinidad por 1-2 géneros; la nota depende de esa afinidad.

    Las películas se llaman ``"<Género> NN"`` para poder verificar en los tests
    que las similitudes aprendidas respetan los géneros.
    """
    rng = np.random.default_rng(semilla)
    peliculas = [(f"{g} {i + 1:02d}", gi) for gi, g in enumerate(GENEROS) for i in range(por_genero)]
    calidad = rng.normal(0, 0.4, len(peliculas))  # algunas películas son mejores en general
    filas = []
    for u in range(n_usuarios):
        # Afinidad +1 en 1 o 2 géneros elegidos al azar y −1 en el resto (integers(1, 3) → 1 o 2).
        afinidad = np.full(len(GENEROS), -1.0)
        afinidad[rng.choice(len(GENEROS), size=rng.integers(1, 3), replace=False)] = 1.0
        sesgo = rng.normal(0, 0.3)  # usuarios más generosos o más exigentes
        for (titulo, g), q in zip(peliculas, calidad):
            # Más probabilidad de ver lo que te gusta (sesgo de selección realista).
            # Con densidad 0.35: 56% de probabilidad de ver un género favorito y 24.5% de los demás.
            p_ver = densidad * (1.6 if afinidad[g] > 0 else 0.7)
            if rng.random() < p_ver:
                # Nota = 3 ± 1.4 por gusto + calidad de la película + sesgo del usuario + ruido;
                # redondeada y recortada a la escala 1-5.
                nota = 3 + 1.4 * afinidad[g] + q + sesgo + rng.normal(0, 0.4)
                filas.append((f"U{u:03d}", titulo, float(np.clip(np.round(nota), 1, 5))))
    return pd.DataFrame(filas, columns=["usuario", "pelicula", "nota"])


def dividir(df: pd.DataFrame, prop_test: float = 0.2, semilla: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split aleatorio por calificación.

    Si a un usuario le quedarían < 2 notas en train, todas sus notas vuelven a
    train (no se puede evaluar a quien el modelo no conoce).
    """
    rng = np.random.default_rng(semilla)
    # Cada calificación va a test con probabilidad prop_test (independiente de las demás).
    es_test = rng.random(len(df)) < prop_test
    df = df.assign(_test=es_test)
    # Si un usuario se quedó con < 2 en train, devolvemos sus notas a train.
    # transform("sum") devuelve, en cada fila, cuántas notas de ese usuario quedaron en train.
    en_train = (~df["_test"]).groupby(df["usuario"]).transform("sum")
    df.loc[en_train < 2, "_test"] = False
    return df[~df["_test"]].drop(columns="_test"), df[df["_test"]].drop(columns="_test")
