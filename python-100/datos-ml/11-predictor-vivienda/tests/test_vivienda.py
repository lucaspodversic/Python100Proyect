"""Tests con datos sintéticos pequeños (rápidos y deterministas)."""

from __future__ import annotations

from pathlib import Path

import pytest

from vivienda import Predictor, comparar_modelos, generar_dataset
from vivienda.cli import main

# Casa de referencia; los tests varían una sola variable por vez para aislar su efecto.
CASA = {"m2": 80, "ambientes": 3, "banos": 1, "antiguedad": 20, "cochera": 0, "distancia_subte_km": 0.5,
        "barrio": "Centro"}


# scope="module": se entrena una sola vez para todos los tests del archivo (ahorra tiempo).
@pytest.fixture(scope="module")
def entrenado() -> Predictor:
    p = Predictor("gbr")
    p.entrenar(generar_dataset(800, semilla=1))
    return p


def test_dataset_reproducible() -> None:
    a, b = generar_dataset(50, 3), generar_dataset(50, 3)
    # Misma semilla → DataFrames idénticos; todos los precios positivos (la fórmula nunca da ≤ 0).
    assert a.equals(b) and a["precio"].gt(0).all()


def test_metricas_razonables(entrenado: Predictor) -> None:
    # Umbrales holgados: con ruido del 7% el techo teórico de R² ronda 0.95; se exige > 0.85
    # y MAPE < 15% (el ruido solo ya aporta ~5-6% de error relativo).
    assert entrenado.metricas["r2"] > 0.85
    assert entrenado.metricas["mape"] < 0.15


def test_relaciones_aprendidas(entrenado: Predictor) -> None:
    chica, grande = entrenado.predecir([CASA, {**CASA, "m2": 160, "ambientes": 5}])
    # Duplicar m² casi duplica el precio en la fórmula (≈ ×1.9 por los montos fijos); se pide > ×1.5.
    assert grande > chica * 1.5
    nueva, vieja = entrenado.predecir([{**CASA, "antiguedad": 0}, {**CASA, "antiguedad": 70}])
    # 0 vs 70 años: factor 1.00 vs 0.72 (−0.4% × 70).
    assert nueva > vieja
    sur, costa = entrenado.predecir([{**CASA, "barrio": "Sur"}, {**CASA, "barrio": "Costa"}])
    # Costa 3800 vs Sur 1500 USD/m² → ×2.5 en la parte proporcional; con los +9000 del baño
    # la relación teórica es ≈ ×2.4 (283 k vs 117 k). Margen hasta ×1.8.
    assert costa > sur * 1.8


def test_barrio_desconocido_y_columnas_faltantes(entrenado: Predictor) -> None:
    # Barrio nunca visto: el one-hot queda en ceros (handle_unknown="ignore") y aún así predice.
    assert entrenado.predecir([{**CASA, "barrio": "Marte"}])[0] > 0
    with pytest.raises(ValueError, match="Faltan columnas"):
        entrenado.predecir([{"m2": 50}])
    with pytest.raises(RuntimeError):
        Predictor().predecir([CASA])


def test_importancias_y_persistencia(entrenado: Predictor, tmp_path: Path) -> None:
    imp = entrenado.importancias()
    # m² es la variable dominante de la fórmula (multiplica todo), así que debe ser la más importante.
    assert imp.index[0] == "num__m2"
    entrenado.guardar(tmp_path / "m.joblib")
    otro = Predictor.cargar(tmp_path / "m.joblib")
    # Ida y vuelta por joblib: el modelo cargado predice lo mismo.
    assert otro.predecir([CASA])[0] == pytest.approx(entrenado.predecir([CASA])[0])


def test_comparar_modelos() -> None:
    r = comparar_modelos(generar_dataset(300, 2), folds=3)
    # Con 300 filas y 3 folds todos superan R² 0.6 (incluso Ridge, lineal sobre log(precio)).
    assert set(r) == {"ridge", "bosque", "gbr"} and all(v > 0.6 for v in r.values())


def test_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    generar_dataset(300).to_csv(tmp_path / "c.csv", index=False)
    assert main(["entrenar", "--csv", str(tmp_path / "c.csv"), "--modelo", "ridge",
                 "--salida", str(tmp_path / "m.joblib")]) == 0
    assert main(["predecir", "--modelo", str(tmp_path / "m.joblib"), "--m2", "80", "--ambientes", "3", "--banos", "1",
                 "--antiguedad", "20", "--cochera", "1", "--distancia", "0.5", "--barrio", "Norte"]) == 0
    assert "Precio estimado: USD" in capsys.readouterr().out
