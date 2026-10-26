"""Aplicación Dash.

La lógica del callback vive en ``actualizar()`` (función pura) para poder
testearla sin levantar un servidor ni un navegador.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from dash import Dash, Input, Output, dcc, html

from .analisis import control_presupuesto, filtrar, kpis
from .graficos import fig_categorias, fig_mensual, fig_saldo

# Montos mensuales en pesos de ejemplo; se pueden pasar otros a crear_app/actualizar.
PRESUPUESTO_DEFECTO = {"Supermercado": 350_000, "Salidas": 80_000, "Transporte": 90_000, "Servicios": 60_000,
                       "Suscripciones": 15_000}


def _moneda(v: float) -> str:
    # Formato argentino: separador de miles con punto ("$ 1.500.000").
    return "$ " + f"{v:,.0f}".replace(",", ".")


def _tarjeta(titulo: str, valor: str, id_: str) -> html.Div:
    return html.Div([html.Div(titulo, className="kpi-titulo"), html.Div(valor, id=id_, className="kpi-valor")],
                    style={"padding": "12px 18px", "border": "1px solid #ddd", "borderRadius": "8px", "minWidth": "180px"})


# Fondo rojo claro, amarillo claro o blanco según el estado de cada categoría.
COLORES_ESTADO = {"excedido": "#ffebee", "cerca": "#fff8e1", "ok": "white"}
COLUMNAS_TABLA = ["categoria", "presupuesto", "real", "uso", "estado"]


def tabla_presupuesto(filas: list[dict[str, Any]]) -> html.Table:
    """Tabla HTML simple coloreada por estado (sin dash_table, que está deprecado)."""
    cabecera = html.Tr([html.Th(c.capitalize(), style={"textAlign": "left", "padding": "4px 10px"}) for c in COLUMNAS_TABLA])
    # Una fila por categoría; sólo las columnas de dinero llevan formato de moneda.
    cuerpo = [html.Tr([html.Td(_moneda(f[c]) if c in ("presupuesto", "real") else f[c], style={"padding": "4px 10px"})
                       for c in COLUMNAS_TABLA], style={"backgroundColor": COLORES_ESTADO.get(f["estado"], "white")})
              for f in filas]
    return html.Table([html.Thead(cabecera), html.Tbody(cuerpo)], style={"borderCollapse": "collapse", "width": "100%"})


def actualizar(df: pd.DataFrame, meses: list[str] | None,
               presupuesto: dict[str, float] = PRESUPUESTO_DEFECTO) -> tuple[Any, ...]:
    """Devuelve (ingresos, gastos, ahorro, tasa, fig_mensual, fig_categorias, fig_saldo, filas_presupuesto)."""
    d = filtrar(df, meses)
    # Filtro sin datos: valores neutros y figuras vacías en lugar de una excepción en el callback.
    if d.empty:
        vacio = {"data": [], "layout": {"title": "Sin datos"}}
        return ("$ 0", "$ 0", "$ 0", "—", vacio, vacio, vacio, [])
    k = kpis(d)
    # reset_index(names=…) convierte el índice (categoría) en columna para la tabla.
    pres = control_presupuesto(d, presupuesto).reset_index(names="categoria")
    pres[["presupuesto", "real"]] = pres[["presupuesto", "real"]].round(0)
    # 0.91 → "91 %": el uso se muestra ya formateado como texto.
    pres["uso"] = (pres["uso"] * 100).round(0).astype(int).astype(str) + " %"
    return (_moneda(k["ingresos"]), _moneda(k["gastos"]), _moneda(k["ahorro"]), f"{k['tasa_ahorro']:.0%}",
            fig_mensual(d), fig_categorias(d), fig_saldo(d), pres.to_dict("records"))


def crear_app(df: pd.DataFrame, presupuesto: dict[str, float] = PRESUPUESTO_DEFECTO) -> Dash:
    app = Dash(__name__, title="Finanzas personales")
    # Los meses "AAAA-MM" ordenan bien como texto (orden cronológico).
    meses = sorted(df["mes"].unique())
    app.layout = html.Div(style={"fontFamily": "system-ui, sans-serif", "maxWidth": "1200px", "margin": "auto"}, children=[
        html.H1("💰 Finanzas personales"),
        dcc.Dropdown(id="filtro-meses", options=[{"label": m, "value": m} for m in meses], multi=True,
                     placeholder="Todos los meses"),
        html.Div(style={"display": "flex", "gap": "12px", "margin": "16px 0", "flexWrap": "wrap"}, children=[
            _tarjeta("Ingresos", "", "kpi-ingresos"), _tarjeta("Gastos", "", "kpi-gastos"),
            _tarjeta("Ahorro", "", "kpi-ahorro"), _tarjeta("Tasa de ahorro", "", "kpi-tasa")]),
        dcc.Graph(id="g-mensual"),
        html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "12px"},
                 children=[dcc.Graph(id="g-categorias"), dcc.Graph(id="g-saldo")]),
        html.H3("Presupuesto mensual"),
        html.Div(id="t-presupuesto"),
    ])

    # Un solo callback: cada cambio del filtro recalcula las 8 salidas a la vez, en el orden de actualizar().
    @app.callback(
        [Output("kpi-ingresos", "children"), Output("kpi-gastos", "children"), Output("kpi-ahorro", "children"),
         Output("kpi-tasa", "children"), Output("g-mensual", "figure"), Output("g-categorias", "figure"),
         Output("g-saldo", "figure"), Output("t-presupuesto", "children")],
        Input("filtro-meses", "value"))
    def _cb(meses_sel: list[str] | None) -> tuple[Any, ...]:
        # El último elemento son filas (dicts) y se convierten acá en la tabla HTML.
        *resto, filas = actualizar(df, meses_sel, presupuesto)
        return (*resto, tabla_presupuesto(filas))

    return app
