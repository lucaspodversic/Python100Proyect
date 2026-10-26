"""Tests de detección de fraude (datos sintéticos, deterministas)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from fraude import Costos, DetectorFraude, comparar, costo_total, generar_transacciones, umbral_minimo_costo, umbral_para_recall
from fraude.cli import main
from fraude.modelo import dividir


@pytest.fixture(scope="module")
def datos() -> pd.DataFrame:
    # scope="module": se genera una sola vez para todos los tests (ahorra tiempo).
    return generar_transacciones(30000)


def test_datos_desbalanceados(datos: pd.DataFrame) -> None:
    # Prevalencia ~1% (≈ 300 fraudes); misma semilla → mismos datos.
    assert 0.007 < datos["fraude"].mean() < 0.013
    assert datos.equals(generar_transacciones(30000))
    train, val, test = dividir(datos)
    # 60% de 30.000 = 18.000; la estratificación deja tasas casi iguales en val y test.
    assert len(train) == 18000 and abs(val["fraude"].mean() - test["fraude"].mean()) < 0.002


def test_funciones_de_umbral_a_mano() -> None:
    y = np.array([1, 1, 0, 0, 0])
    p = np.array([0.9, 0.3, 0.6, 0.1, 0.2])
    m = np.array([100.0, 200.0, 50.0, 10.0, 10.0])
    # Ejemplo de 5 filas: fraudes en 0 (p=0.9, $100) y 1 (p=0.3, $200); legítimas con p 0.6, 0.1, 0.2.
    c = Costos(revision=1, friccion_fp=2)
    # umbral 0.5: alerta {0, 2}; FN = fila 1 ($200); 2 revisiones; 1 FP.
    assert costo_total(y, p, m, 0.5, c) == 200 + 2 * 1 + 1 * 2
    # Con umbral en (0.2, 0.3]: alertas {0, 1, 2} → 0 FN + 3 revisiones + 1 FP = 5 (el mínimo posible).
    u, costo = umbral_minimo_costo(y, p, m, c)
    assert u <= 0.3 and costo == 0 + 3 * 1 + 1 * 2  # atrapa ambos fraudes, 1 FP
    # recall 0.5 → atrapar ceil(0.5·2) = 1 fraude → umbral 0.9; recall 1.0 → los 2 → 0.3.
    assert umbral_para_recall(y, p, 0.5) == 0.9 and umbral_para_recall(y, p, 1.0) == 0.3
    with pytest.raises(ValueError):
        # Sin positivos no se puede calcular recall → ValueError.
        umbral_para_recall(np.zeros(3), p[:3], 0.5)


def test_paradoja_de_la_exactitud_y_mejora_por_umbral(datos: pd.DataFrame) -> None:
    t = comparar(datos)
    assert t.loc["nunca_fraude", "exactitud"] > 0.98  # ¡alta exactitud y no sirve!
    for tipo in ("logistica", "boosting"):
        # PR-AUC del baseline = prevalencia ≈ 0.01; los modelos deben superarla por más de 20 veces.
        assert t.loc[f"{tipo}@0.5", "pr_auc"] > 20 * t.loc["nunca_fraude", "pr_auc"]  # azar = prevalencia
        # El umbral elegido por costo (en validación) baja el costo en test frente a 0.5 y a no hacer nada.
        assert t.loc[f"{tipo}@costo", "costo"] < t.loc[f"{tipo}@0.5", "costo"]
        assert t.loc[f"{tipo}@costo", "costo"] < 0.6 * t.loc["nunca_fraude", "costo"]
        assert t.loc[f"{tipo}@costo", "precision"] > t.loc[f"{tipo}@0.5", "precision"]


def test_criterio_recall(datos: pd.DataFrame) -> None:
    train, val, test = dividir(datos)
    d = DetectorFraude("boosting").entrenar(train, val, criterio="recall", recall_min=0.9)
    rv = d.evaluar(val)
    assert rv["recall"] >= 0.9
    rt = d.evaluar(test)
    # Precisión > 3 veces la prevalencia: las alertas son mucho más ricas en fraude que el azar.
    assert rt["recall"] >= 0.7  # generaliza razonablemente (algo menos que en validación)
    assert rt["precision"] > 3 * test["fraude"].mean()
    with pytest.raises(ValueError):
        DetectorFraude("logistica").entrenar(train, val, criterio="otro")
    with pytest.raises(RuntimeError):
        # Usar un detector sin entrenar → RuntimeError.
        DetectorFraude().probabilidad(test)


def test_persistencia_y_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ruta = tmp_path / "d.joblib"
    # n chico y logística para que el test de CLI sea rápido.
    assert main(["entrenar", "--n", "8000", "--salida", str(ruta), "--tipo", "logistica"]) == 0
    assert "Umbral elegido" in capsys.readouterr().out
    # Transacciones nuevas sin la etiqueta, como llegarían en producción.
    nuevas = generar_transacciones(500, semilla=5).drop(columns="fraude")
    nuevas.to_csv(tmp_path / "t.csv", index=False)
    assert main(["puntuar", "--modelo", str(ruta), str(tmp_path / "t.csv"), "--salida", str(tmp_path / "o.csv")]) == 0
    out = pd.read_csv(tmp_path / "o.csv")
    # La salida trae las columnas nuevas y queda ordenada de mayor a menor probabilidad.
    assert {"prob_fraude", "alerta"} <= set(out.columns) and out["prob_fraude"].is_monotonic_decreasing
    d = DetectorFraude.cargar(ruta)
    assert np.allclose(d.probabilidad(nuevas), DetectorFraude.cargar(ruta).probabilidad(nuevas))
