"""Datos de ventas: generador sintético y carga desde CSV."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def generar_ventas(meses: int = 72, semilla: int = 0, inicio: str = "2019-01-01") -> pd.Series:
    """Ventas mensuales = nivel · tendencia · estacionalidad (picos en diciembre y julio) · ruido.

    Multiplicativa como en el comercio real: la amplitud estacional crece con el nivel.
    """
    rng = np.random.default_rng(semilla)
    t = np.arange(meses)
    # Nivel inicial 1000 con crecimiento compuesto del 1,2% mensual (≈ 15% anual).
    tendencia = 1000 * (1 + 0.012) ** t
    # Índice 0-11 del mes calendario de cada punto, aunque la serie no empiece en enero.
    mes = (t + pd.Timestamp(inicio).month - 1) % 12
    # Factor por mes (ene…dic): febrero el más bajo (0.8), julio 1.15 (vacaciones), diciembre 1.45 (fiestas).
    perfil = np.array([0.85, 0.8, 0.9, 0.95, 1.0, 1.0, 1.15, 1.0, 0.95, 1.0, 1.1, 1.45])
    # Ruido multiplicativo de ±3% típico; "MS" = month start (fechas el día 1 de cada mes).
    ruido = rng.normal(1, 0.03, meses)
    idx = pd.date_range(inicio, periods=meses, freq="MS")
    return pd.Series(np.round(tendencia * perfil[mes] * ruido, 1), index=idx, name="ventas")


def cargar_csv(ruta: Path | str, col_fecha: str = "fecha", col_valor: str = "ventas", frecuencia: str = "MS") -> pd.Series:
    """Lee transacciones o totales y los agrega a la frecuencia pedida (por defecto mensual).

    Los meses sin ventas quedan en 0 (no NaN): para ventas, "no hubo" = 0.
    """
    # resample(...).sum() suma las transacciones de cada mes y crea los meses faltantes con 0.
    df = pd.read_csv(ruta, parse_dates=[col_fecha])
    s = df.set_index(col_fecha)[col_valor].astype(float).resample(frecuencia).sum()
    s.name = "ventas"
    return s
