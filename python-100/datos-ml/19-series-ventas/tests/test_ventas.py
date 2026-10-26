"""Tests de pronóstico (datos sintéticos, sin red)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ventas import NaiveEstacional, backtest, cargar_csv, generar_ventas, metricas, pronosticar
from ventas.cli import main
from ventas.graficos import graficar
from ventas.modelos import ModeloNoViable, Pronostico


def test_generador_y_csv(tmp_path: Path) -> None:
    s = generar_ventas(48)
    # 48 meses desde enero 2019; "MS" = frecuencia mensual de inicio de mes.
    # Diciembre (×1.45) supera siempre a febrero (×0.8) del mismo año, aun con tendencia y ruido.
    assert len(s) == 48 and s.index.freqstr == "MS"
    assert (s[s.index.month == 12] > s[s.index.month == 2].to_numpy()).all()  # pico de diciembre
    # CSV de transacciones: se agregan por mes y los meses vacíos quedan en 0.
    (tmp_path / "v.csv").write_text("fecha,ventas\n2024-01-05,10\n2024-01-20,5\n2024-03-01,7\n", encoding="utf-8")
    m = cargar_csv(tmp_path / "v.csv")
    # Enero: 10 + 5 = 15; febrero sin transacciones = 0; marzo: 7.
    assert m.tolist() == [15.0, 0.0, 7.0]


def test_naive_estacional_exacto() -> None:
    # Serie 1..12 repetida 3 años (2020-2022): el naive estacional debe copiar el último ciclo.
    s = pd.Series(np.tile(np.arange(1.0, 13.0), 3), index=pd.date_range("2020-01-01", periods=36, freq="MS"))
    p = NaiveEstacional().ajustar_y_pronosticar(s, 14)
    # 14 pasos = 12 del ciclo + enero y febrero otra vez; el pronóstico arranca en enero 2023.
    assert p.media.tolist() == list(np.arange(1.0, 13.0)) + [1.0, 2.0]
    assert p.media.index[0] == pd.Timestamp("2023-01-01")


def test_sarima_auto_supera_al_naive() -> None:
    s = generar_ventas(72)
    # 60 meses de entrenamiento (≥ 36, SARIMA viable) y el último año como prueba.
    train, test = s.iloc[:-12], s.iloc[-12:]
    p = pronosticar(train, 12)
    assert p.modelo == "sarima" and any("orden elegido" in n for n in p.notas)
    m_sar = metricas(test.to_numpy(), p.media.to_numpy(), train.to_numpy())
    m_nai = metricas(test.to_numpy(), pronosticar(train, 12, "naive").media.to_numpy(), train.to_numpy())
    # El naive ignora la tendencia (+1,2%/mes ≈ 15% anual): SARIMA debe errar menos (< 5% con ruido de 3%).
    assert m_sar["mape"] < 5 and m_sar["mae"] < m_nai["mae"]
    assert (p.inferior < p.media).all() and (p.media < p.superior).all()


def test_fallback_por_serie_corta_y_por_excepcion() -> None:
    corta = generar_ventas(30)  # < 36: SARIMA no viable, Holt-Winters sí
    p = pronosticar(corta, 6)
    assert p.modelo == "holt_winters" and "sarima descartado" in p.notas[0]
    # 14 < 24: también se descarta Holt-Winters → queda el naive, con 2 notas (sarima y holt_winters).
    muy_corta = generar_ventas(14)
    p2 = pronosticar(muy_corta, 6)
    assert p2.modelo == "naive_estacional" and len(p2.notas) == 2

    # Modelo que lanza una excepción inesperada (no ModeloNoViable): debe activar igual el fallback.
    class Roto:
        nombre = "roto"

        def ajustar_y_pronosticar(self, serie: pd.Series, horizonte: int) -> Pronostico:
            raise np.linalg.LinAlgError("matriz singular")

    p3 = pronosticar(generar_ventas(40), 3, cadena=[Roto(), NaiveEstacional()])
    assert p3.modelo == "naive_estacional" and "LinAlgError" in p3.notas[0]
    con_ceros = generar_ventas(40)
    # Un cero impide el log de SARIMA → cae al naive de respaldo.
    con_ceros.iloc[5] = 0
    assert pronosticar(con_ceros, 3, "sarima").modelo == "naive_estacional"
    with pytest.raises(ValueError):
        # horizonte 0 inválido → ValueError; cadena sin alternativas que funcionen → RuntimeError.
        pronosticar(corta, 0)
    with pytest.raises(RuntimeError):
        pronosticar(corta, 3, cadena=[Roto()])
    assert issubclass(ModeloNoViable, RuntimeError)


def test_backtest_y_grafico(tmp_path: Path) -> None:
    # 2 orígenes (cortes en 60 y 66 meses), evaluando 6 meses cada uno.
    r = backtest(generar_ventas(72), ["sarima", "naive"], horizonte=6, origenes=2)
    assert set(r.index) == {"sarima", "naive"}
    # El naive fuera de muestra debe tener un MASE razonable (cerca de 1); SARIMA, menor.
    assert r.loc["sarima", "mase"] < r.loc["naive", "mase"] and 0.05 < r.loc["naive", "mase"] < 5
    s = generar_ventas(48)
    ruta = graficar(s, pronosticar(s, 6, "naive"), tmp_path / "g.png")
    # Los primeros bytes de todo PNG son la firma \x89PNG.
    assert ruta.read_bytes()[:4] == b"\x89PNG"


def test_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["pronosticar", "--demo", "--horizonte", "3", "--modelo", "holt_winters",
                 "--grafico", str(tmp_path / "p.png")]) == 0
    # 72 meses de demo: Holt-Winters viable; la tabla incluye la columna inf_80.
    out = capsys.readouterr().out
    assert "holt_winters" in out and "inf_80" in out and (tmp_path / "p.png").exists()
