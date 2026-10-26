"""Cálculos puros (sin gráficos) para que sean fáciles de testear."""

from __future__ import annotations

import pandas as pd


def filtrar(df: pd.DataFrame, meses: list[str] | None) -> pd.DataFrame:
    # None o lista vacía (dropdown sin selección) = todos los meses.
    return df if not meses else df[df["mes"].isin(meses)]


def resumen_mensual(df: pd.DataFrame) -> pd.DataFrame:
    """Ingresos, gastos (positivos), ahorro y tasa de ahorro por mes."""
    g = df.groupby("mes")["monto"]
    # Los gastos vienen negativos en el CSV; se muestran como positivos para graficarlos junto a ingresos.
    r = pd.DataFrame({"ingresos": g.apply(lambda s: s[s > 0].sum()), "gastos": g.apply(lambda s: -s[s < 0].sum())})
    r["ahorro"] = r["ingresos"] - r["gastos"]
    # Meses sin ingresos → NaN en lugar de una división por cero (±inf).
    r["tasa_ahorro"] = (r["ahorro"] / r["ingresos"]).where(r["ingresos"] > 0)
    return r


def gastos_por_categoria(df: pd.DataFrame) -> pd.Series:
    gastos = df[df["monto"] < 0]
    # Signo invertido (gasto positivo) y de mayor a menor: la categoría que más pesa primero.
    return (-gastos.groupby("categoria")["monto"].sum()).sort_values(ascending=False)


def kpis(df: pd.DataFrame) -> dict[str, float]:
    ingresos = float(df.loc[df["monto"] > 0, "monto"].sum())
    gastos = float(-df.loc[df["monto"] < 0, "monto"].sum())
    # max(…, 1): un DataFrame vacío no provoca división por cero en el promedio mensual.
    meses = max(df["mes"].nunique(), 1)
    return {"ingresos": ingresos, "gastos": gastos, "ahorro": ingresos - gastos,
            "tasa_ahorro": (ingresos - gastos) / ingresos if ingresos else 0.0,
            "gasto_mensual_promedio": gastos / meses}


def control_presupuesto(df: pd.DataFrame, presupuesto: dict[str, float]) -> pd.DataFrame:
    """Compara el gasto mensual PROMEDIO por categoría contra el presupuesto mensual."""
    meses = max(df["mes"].nunique(), 1)
    # Promedio mensual para comparar con un presupuesto que también es mensual.
    real = gastos_por_categoria(df) / meses
    # Unión por categoría: sin gasto → real 0; categorías sin presupuesto se filtran en la línea siguiente.
    t = pd.DataFrame({"presupuesto": pd.Series(presupuesto), "real": real}).fillna(0)
    t = t[t["presupuesto"] > 0]
    t["uso"] = t["real"] / t["presupuesto"]
    # Intervalos cerrados a derecha: ≤ 80% "ok", (80%, 100%] "cerca", > 100% "excedido".
    # El límite inferior −1 incluye el uso 0 (categoría sin gastos).
    t["estado"] = pd.cut(t["uso"], [-1, 0.8, 1.0, float("inf")], labels=["ok", "cerca", "excedido"]).astype(str)
    return t.sort_values("uso", ascending=False)
