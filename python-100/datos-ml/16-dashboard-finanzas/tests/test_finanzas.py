"""Tests de carga, análisis, figuras y callback del dashboard (sin servidor)."""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import pytest

from finanzas import cargar_movimientos, categorizar, control_presupuesto, generar_demo, kpis, resumen_mensual
from finanzas.app import actualizar, crear_app, tabla_presupuesto
from finanzas.cli import main

# Exportación típica de home banking argentino: separador ";", montos "1.000.000,00",
# columnas Débito/Crédito con tilde y fechas dd/mm/aaaa.
CSV_AR = """Fecha;Concepto;Débito;Crédito
01/03/2025;Haberes ACME;;1.000.000,00
05/03/2025;Alquiler;300.000,00;
10/03/2025;COTO SUC 123;45.500,50;
02/04/2025;Haberes ACME;;1.000.000,00
15/04/2025;Netflix;12.000,00;
"""


def test_carga_formato_home_banking() -> None:
    df = cargar_movimientos(io.StringIO(CSV_AR))
    # Crédito positivo y débito negativo; "45.500,50" → 45500.5.
    assert df["monto"].tolist() == [1_000_000.0, -300_000.0, -45_500.5, 1_000_000.0, -12_000.0]
    # Por palabras clave: haberes → Sueldo, alquiler → Vivienda, coto → Supermercado, netflix → Suscripciones.
    assert df["categoria"].tolist() == ["Sueldo", "Vivienda", "Supermercado", "Sueldo", "Suscripciones"]
    assert df["mes"].tolist() == ["2025-03"] * 3 + ["2025-04"] * 2
    assert set(df["tipo"]) == {"Ingreso", "Gasto"}


def test_carga_formato_simple_y_errores(tmp_path: Path) -> None:
    p = tmp_path / "m.csv"
    p.write_text("fecha,descripcion,monto,categoria\n2025-01-02,Uber,-1500.5,\n2025-01-03,Regalo,200,Extras\n",
                 encoding="utf-8")
    df = cargar_movimientos(p)
    # Categoría vacía en Uber → se infiere; "Extras" puesta por el usuario se respeta.
    assert df["categoria"].tolist() == ["Transporte", "Extras"]
    # Sin monto ni débito/crédito → ValueError.
    p.write_text("fecha,descripcion\n2025-01-01,x\n", encoding="utf-8")
    with pytest.raises(ValueError):
        cargar_movimientos(p)
    assert categorizar("Transferencia recibida", 10) == "Otros ingresos"


def test_resumen_kpis_y_presupuesto() -> None:
    df = cargar_movimientos(io.StringIO(CSV_AR))
    r = resumen_mensual(df)
    # Marzo: 300.000 + 45.500,50. Abril: (1.000.000 − 12.000) / 1.000.000 = 0.988.
    assert r.loc["2025-03", "gastos"] == pytest.approx(345_500.5)
    assert r.loc["2025-04", "tasa_ahorro"] == pytest.approx(0.988)
    k = kpis(df)
    # Total: 2 sueldos menos todos los gastos (345.500,5 + 12.000).
    assert k["ahorro"] == pytest.approx(2_000_000 - 357_500.5)
    # Promedios mensuales (2 meses): súper 22.750, suscripciones 6.000, vivienda 150.000.
    t = control_presupuesto(df, {"Supermercado": 25_000, "Suscripciones": 20_000, "Vivienda": 100_000, "Salud": 1})
    # 22.750 / 25.000 = 0.91 (entre 0.8 y 1); 6.000 / 20.000 = 0.3; 150.000 / 100.000 = 1.5.
    assert t.loc["Supermercado", "estado"] == "cerca"  # 91 %
    assert t.loc["Suscripciones", "estado"] == "ok"  # 30 %
    assert t.loc["Vivienda", "estado"] == "excedido"  # 150 %
    # Salud no tiene gastos: uso 0 → "ok". La tabla está ordenada por uso: Vivienda (150%) primero.
    assert t.loc["Salud", "estado"] == "ok" and t.index[0] == "Vivienda"


def test_demo_y_callback() -> None:
    df = generar_demo(4)
    # La demo genera un sueldo por mes.
    assert df["mes"].nunique() == 4 and (df["categoria"] == "Sueldo").sum() == 4
    res = actualizar(df, ["2025-02"])
    assert res[0].startswith("$ ") and res[3].endswith("%")
    # fig_mensual tiene 3 trazas (ingresos, gastos, ahorro); fig_categorias es una torta.
    assert len(res[4].data) == 3 and res[5].data[0].type == "pie"
    assert all("estado" in fila for fila in res[7])
    # Mes inexistente → rama de datos vacíos.
    vacio = actualizar(df, ["1999-01"])
    assert vacio[0] == "$ 0" and vacio[7] == []


def test_layout_de_la_app() -> None:
    app = crear_app(generar_demo(2))
    ids = {getattr(c, "id", None) for c in _recorrer(app.layout)}
    assert {"filtro-meses", "kpi-ingresos", "g-mensual", "g-categorias", "g-saldo", "t-presupuesto"} <= ids
    tabla = tabla_presupuesto(actualizar(generar_demo(2), None)[7])
    assert len(_recorrer(tabla)) > 5


# Recorre el árbol de componentes Dash (children puede ser lista, componente o texto).
def _recorrer(nodo: object) -> list[object]:
    hijos = getattr(nodo, "children", None)
    lista = hijos if isinstance(hijos, list) else ([hijos] if hijos is not None and not isinstance(hijos, str) else [])
    return [nodo] + [x for h in lista for x in _recorrer(h)]


def test_cli_exporta_html(tmp_path: Path) -> None:
    assert main(["--demo", "--exportar", str(tmp_path / "r.html")]) == 0
    html = (tmp_path / "r.html").read_text(encoding="utf-8")
    assert "plotly" in html.lower() and "Finanzas personales" in html
