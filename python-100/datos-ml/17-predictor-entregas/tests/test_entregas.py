"""Tests del predictor de entregas (datos sintéticos, deterministas)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from entregas import PredictorEntregas, evaluar, generar_pedidos
from entregas.cli import main


@pytest.fixture(scope="module")
def modelo() -> PredictorEntregas:
    # 150 árboles (en lugar de 300) para que el test sea rápido; alcanza para estas relaciones.
    return PredictorEntregas(n_estimadores=150).entrenar(generar_pedidos(2000))


# Pedido de referencia a las 16 hs (fuera de los picos); cada test cambia una sola variable.
BASE = dict(distancia_km=4.0, hora=16, dia_semana=2, clima="despejado", vehiculo="moto", pedidos_activos=1,
            preparacion_min=14.0)


def test_datos_validos() -> None:
    df = generar_pedidos(500)
    # Preparación ≥ 4 min y el ruido nunca baja de −3, así que toda duración es positiva.
    assert len(df) == 500 and df["duracion_min"].gt(0).all()
    assert df.equals(generar_pedidos(500))  # determinista


def test_supera_baselines_y_cobertura() -> None:
    r = evaluar(generar_pedidos(2000))
    # La relación es no lineal (distancia / velocidad, picos gaussianos): el GBR debe ganarle a la
    # lineal, y ambos a la media. Se exige además un 40% menos de error que la media.
    assert r["mae_gbr"] < r["mae_lineal"] < r["mae_media"]
    assert r["mae_gbr"] < 0.6 * r["mae_media"]
    # Rango tolerante: los cuantiles estimados con datos finitos no dan exactamente 80%.
    assert 0.65 <= r["cobertura_p10_p90"] <= 0.92  # nominal 80 %


def test_relaciones_aprendidas(modelo: PredictorEntregas) -> None:
    def est(**cambios: object) -> float:
        return modelo.predecir_uno(**{**BASE, **cambios}).estimado_min

    # En moto con buen tiempo, 7 km extra = 7 / 28 × 60 = 15 min de diferencia teórica; se pide > 8.
    assert est(distancia_km=9.0) > est(distancia_km=2.0) + 8
    # 4 km a 28 km/h = 8.6 min; con tormenta (28 × 0.55 = 15.4 km/h) = 15.6 min → +7 teóricos.
    assert est(clima="tormenta") > est(clima="despejado") + 3
    # Bici a 14 km/h: 17.1 min de trayecto vs 8.6 en moto.
    assert est(vehiculo="bici") > est(vehiculo="moto")
    # Congestión a las 21 ≈ 9·e^(−0.25/3) ≈ 8.3 min; a las 16 prácticamente 0.
    assert est(hora=21) > est(hora=16)  # hora pico nocturna


def test_intervalo_ordenado(modelo: PredictorEntregas) -> None:
    pred = modelo.predecir(generar_pedidos(200, semilla=9))
    # Gracias al ordenamiento en predecir(), p10 ≤ estimado ≤ p90 siempre, aunque los modelos se crucen.
    assert (pred["p10"] <= pred["estimado"]).all() and (pred["estimado"] <= pred["p90"]).all()
    assert "Llega en" in modelo.predecir_uno(**BASE).texto()


def test_importancias_y_persistencia(modelo: PredictorEntregas, tmp_path: Path) -> None:
    # El trayecto es el término de mayor variación en la fórmula, por eso la distancia domina.
    assert modelo.importancias().index[0] == "distancia_km"
    modelo.guardar(tmp_path / "m.joblib")
    otro = PredictorEntregas.cargar(tmp_path / "m.joblib")
    x = pd.DataFrame([BASE])
    # El modelo cargado desde disco debe dar exactamente las mismas predicciones.
    assert otro.predecir(x).equals(modelo.predecir(x))


def test_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ruta = tmp_path / "m.joblib"
    assert main(["entrenar", "--salida", str(ruta), "--n", "600"]) == 0
    assert main(["predecir", "--modelo", str(ruta), "--distancia", "3", "--clima", "lluvia"]) == 0
    assert "Llega en" in capsys.readouterr().out
