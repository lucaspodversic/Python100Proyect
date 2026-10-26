"""Tests de modelos de recomendación con datos sintéticos de gustos conocidos."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from recomendador import (BaselineSesgos, Calificaciones, FactorizacionMatricial, ItemKNN, dividir,
                          generar_calificaciones, populares, precision_at_k, rmse)
from recomendador.cli import main
from recomendador.modelos import recomendar


@pytest.fixture(scope="module")
def particion() -> tuple[Calificaciones, pd.DataFrame]:
    # 200 usuarios × 50 películas con gustos por género conocidos; 20% de las notas a test.
    df = generar_calificaciones(200, 10, 0.35, semilla=1)
    train, test = dividir(df, 0.2, semilla=1)
    c = Calificaciones.desde_df(train, sorted(df["usuario"].unique()), sorted(df["pelicula"].unique()))
    return c, test


def test_matriz_y_division() -> None:
    df = pd.DataFrame({"usuario": ["a", "a", "b"], "pelicula": ["x", "y", "x"], "nota": [5.0, 3.0, 1.0]})
    c = Calificaciones.desde_df(df)
    # b no vio "y" → NaN en (1, 1); a puso 5 a "x" → (0, 0).
    assert c.usuarios == ["a", "b"] and np.isnan(c.matriz[1, 1]) and c.matriz[0, 0] == 5
    g = generar_calificaciones(30, 4, semilla=2)
    tr, te = dividir(g, 0.3, semilla=2)
    assert len(tr) + len(te) == len(g)
    total, en_train = g.groupby("usuario").size(), tr.groupby("usuario").size()
    # Quien tenía ≥ 2 notas conserva al menos 2 en train; quien tenía 1 la conserva.
    assert (en_train >= total.clip(upper=2)).all()  # nadie queda con < 2 (o con menos de las que tenía)


def test_modelos_superan_media_global(particion: tuple[Calificaciones, pd.DataFrame]) -> None:
    c, test = particion
    # Referencia trivial: predecir siempre la media global.
    media = np.full(c.matriz.shape, np.nanmean(c.matriz))
    e_media = rmse(media, c, test)
    e_base = rmse(BaselineSesgos().ajustar(c).predecir_matriz(), c, test)
    e_knn = rmse(ItemKNN().ajustar(c).predecir_matriz(), c, test)
    mf = FactorizacionMatricial(epocas=40).ajustar(c)
    e_mf = rmse(mf.predecir_matriz(), c, test)
    assert e_base < e_media
    # La nota depende sobre todo de la afinidad por género (±1.4), que los sesgos no capturan:
    # KNN y MF deben mejorar el RMSE del baseline al menos un 10%.
    assert e_knn < e_base * 0.9 and e_mf < e_base * 0.9  # capturan los gustos, no sólo sesgos
    assert mf.historial[-1] < mf.historial[0]  # el SGD converge


def test_precision_ranking(particion: tuple[Calificaciones, pd.DataFrame]) -> None:
    c, test = particion
    p_knn = precision_at_k(ItemKNN().ajustar(c).predecir_matriz(), c, test, k=3)
    rng = np.random.default_rng(0)
    # Ranking aleatorio como referencia; KNN debe superarlo por más de 10 puntos.
    p_azar = precision_at_k(rng.random(c.matriz.shape), c, test, k=3)
    assert p_knn > p_azar + 0.1


def test_similares_respetan_genero(particion: tuple[Calificaciones, pd.DataFrame]) -> None:
    knn = ItemKNN().ajustar(particion[0])
    # Los usuarios que disfrutan un género lo disfrutan entero, así que los 3 vecinos
    # más similares deben ser del mismo género.
    for peli in ("Terror 01", "Comedia 02"):
        genero = peli.split()[0]
        vecinos = [p for p, _ in knn.similares(peli, 3)]
        assert all(v.startswith(genero) for v in vecinos), vecinos


def test_recomendar_excluye_vistas_y_populares(particion: tuple[Calificaciones, pd.DataFrame]) -> None:
    c, _ = particion
    knn = ItemKNN().ajustar(c)
    u = c.usuarios[0]
    vistas = {c.peliculas[i] for i in np.nonzero(~np.isnan(c.matriz[0]))[0]}
    recs = recomendar(knn, c, u, 5)
    # Intersección vacía: ninguna recomendada estaba ya vista.
    assert len(recs) == 5 and not vistas & {p for p, _ in recs}
    # Promedio bayesiano: una película con un único 5 no gana.
    df = pd.DataFrame({"usuario": ["a", "b", "c", "a", "b", "c", "d"], "pelicula": ["x", "x", "x", "y", "y", "y", "z"],
                       "nota": [4.5, 5, 4.5, 2, 3, 2, 5.0]})
    # Media global = 26/7 ≈ 3.71. Con m=2: x = (3·4.67 + 2·3.71)/5 ≈ 4.29;
    # z (un solo 5) = (5 + 2·3.71)/3 ≈ 4.14 → gana x.
    assert populares(Calificaciones.desde_df(df), 1, m=2)[0][0] == "x"


def test_cli(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["evaluar"]) == 0
    assert main(["recomendar", "U001", "-n", "3"]) == 0
    # Usuario inexistente → rama de arranque en frío ("Usuario nuevo").
    assert main(["recomendar", "NUEVO"]) == 0
    assert main(["similares", "Drama 01", "-n", "2"]) == 0
    out = capsys.readouterr().out
    assert "item-knn" in out and "Usuario nuevo" in out
