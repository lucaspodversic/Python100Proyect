"""Figuras Plotly (devuelven ``go.Figure``; Dash las renderiza)."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .analisis import gastos_por_categoria, resumen_mensual


def fig_mensual(df: pd.DataFrame) -> go.Figure:
    r = resumen_mensual(df).reset_index()
    # Barras agrupadas de ingresos (verde) y gastos (rojo) más la línea de ahorro por mes.
    fig = go.Figure([go.Bar(name="Ingresos", x=r["mes"], y=r["ingresos"], marker_color="#2e7d32"),
                     go.Bar(name="Gastos", x=r["mes"], y=r["gastos"], marker_color="#c62828"),
                     go.Scatter(name="Ahorro", x=r["mes"], y=r["ahorro"], mode="lines+markers")])
    fig.update_layout(title="Ingresos vs. gastos por mes", barmode="group", yaxis_tickprefix="$ ",
                      template="plotly_white")
    return fig


def fig_categorias(df: pd.DataFrame) -> go.Figure:
    s = gastos_por_categoria(df).reset_index(name="gasto")
    # hole=0.45 lo convierte en gráfico de dona.
    fig = px.pie(s, names="categoria", values="gasto", hole=0.45, title="Gastos por categoría")
    fig.update_traces(textinfo="percent+label")
    return fig


def fig_saldo(df: pd.DataFrame) -> go.Figure:
    # Neto por día y suma acumulada = saldo a lo largo del tiempo (partiendo de 0).
    diario = df.groupby(df["fecha"].dt.date)["monto"].sum().cumsum()
    fig = px.area(x=diario.index, y=diario.values, labels={"x": "Fecha", "y": "Saldo acumulado"},
                  title="Evolución del saldo")
    fig.update_layout(template="plotly_white", yaxis_tickprefix="$ ")
    return fig
