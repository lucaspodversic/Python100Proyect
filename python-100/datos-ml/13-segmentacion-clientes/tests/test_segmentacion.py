"""Tests: RFM a mano y recuperación de perfiles latentes."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from sklearn.metrics import adjusted_rand_score

from segmentacion import Segmentador, calcular_rfm, elegir_k, generar_transacciones
from segmentacion.cli import main


def test_rfm_calculo_exacto() -> None:
    tx = pd.DataFrame({"cliente": ["a", "a", "b", "b"],
                       "fecha": ["2024-12-01", "2024-12-25", "2024-06-01", "2024-07-01"],
                       "monto": [10.0, 30.0, 100.0, -100.0]})  # la devolución se ignora
    rfm = calcular_rfm(tx, referencia="2025-01-01")
    # a: última compra 25/12 → 7 días hasta el 01/01; 2 compras; 10 + 30 = 40.
    assert rfm.loc["a"].tolist() == [7, 2, 40.0]
    # b: el −100 del 01/07 se descarta, queda la compra del 01/06 → 214 días
    # (jun 29 + jul 31 + ago 31 + sep 30 + oct 31 + nov 30 + dic 31); 1 compra; 100.
    assert rfm.loc["b"].tolist() == [214, 1, 100.0]
    with pytest.raises(ValueError):
        calcular_rfm(tx.drop(columns="monto"))


@pytest.fixture(scope="module")
def datos() -> tuple[pd.DataFrame, pd.Series]:
    # 50 clientes × 4 perfiles = 200 clientes, con su perfil real conocido.
    tx, perfiles = generar_transacciones(50, semilla=1)
    return calcular_rfm(tx, "2025-01-01"), perfiles


def test_elegir_k_con_silueta(datos: tuple[pd.DataFrame, pd.Series]) -> None:
    k, puntajes = elegir_k(datos[0], k_max=7)
    # Hay 4 perfiles latentes: k elegido cerca de 4. Se evaluó cada k de 3 a 7.
    assert 3 <= k <= 5 and set(puntajes) == set(range(3, 8))
    assert all(0.3 < v <= 1 for v in puntajes.values())  # estructura clara en los datos


def test_recupera_perfiles_y_nombres(datos: tuple[pd.DataFrame, pd.Series]) -> None:
    rfm, perfiles = datos
    res = Segmentador(4).ajustar(rfm)
    # ARI: 1 = coincidencia perfecta con los perfiles reales, ~0 = azar. > 0.7 = buena recuperación.
    assert adjusted_rand_score(perfiles.loc[res.index], res["cluster"]) > 0.7
    # Cada perfil real debería caer mayormente en el segmento esperado.
    # Mapeo lógico según PERFILES: vip (40 compras, 250 de ticket) → Campeones;
    # perdido (300 días) → Dormidos; frecuente (25 compras) → Leales; ocasional → Potenciales.
    esperado = {"vip": "Campeones", "perdido": "Dormidos", "frecuente": "Leales", "ocasional": "Potenciales"}
    mayoria = res.groupby(perfiles.loc[res.index])["segmento"].agg(lambda s: s.mode()[0]).to_dict()
    assert mayoria == esperado
    assert res["campaña"].notna().all()
    resumen = Segmentador.resumen(res)
    # Campeones encabeza el resumen por gasto total y los 200 clientes están asignados.
    assert resumen.index[0] == "Campeones" and resumen["clientes"].sum() == 200


def test_asignar_nuevos_clientes(datos: tuple[pd.DataFrame, pd.Series]) -> None:
    seg = Segmentador(4)
    seg.ajustar(datos[0])
    # Dos casos extremos (sin "fit"): uno claramente VIP y otro claramente perdido.
    nuevos = pd.DataFrame({"recencia": [2, 340], "frecuencia": [45, 1], "monetario": [12000.0, 50.0]},
                          index=["top", "ido"])
    assert seg.asignar(nuevos).to_dict() == {"top": "Campeones", "ido": "Dormidos"}


def test_nombres_con_k_grande(datos: tuple[pd.DataFrame, pd.Series]) -> None:
    res = Segmentador(6).ajustar(datos[0])
    # Con k=6 se nombran los 4 principales y los 2 clusters extra se numeran.
    assert {"Campeones", "Dormidos", "Leales", "Potenciales", "Potenciales 2", "Potenciales 3"} == set(res["segmento"])


def test_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # CLI con CSV real en disco (80 clientes) y k fijo para no depender de la silueta.
    generar_transacciones(20)[0].to_csv(tmp_path / "tx.csv", index=False)
    assert main([str(tmp_path / "tx.csv"), "--k", "4", "--salida", str(tmp_path / "s.csv")]) == 0
    assert "Campeones" in capsys.readouterr().out and (tmp_path / "s.csv").exists()
