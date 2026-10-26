"""CLI::

    dashboard-finanzas movimientos.csv [--puerto 8050]
    dashboard-finanzas --demo
    dashboard-finanzas movimientos.csv --exportar reporte.html   # HTML estático sin servidor
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .datos import cargar_movimientos, generar_demo
from .graficos import fig_categorias, fig_mensual, fig_saldo


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="dashboard-finanzas", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    # CSV opcional porque --demo genera datos propios.
    ap.add_argument("csv", type=Path, nargs="?")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--puerto", type=int, default=8050)
    ap.add_argument("--exportar", type=Path, help="genera un HTML estático en vez de levantar el servidor")
    a = ap.parse_args(argv)
    if not a.demo and a.csv is None:
        ap.error("indicá un CSV o --demo")
    df = generar_demo() if a.demo else cargar_movimientos(a.csv)
    if a.exportar:
        # Plotly.js se incluye (desde el CDN) sólo en la primera figura; las demás lo reutilizan.
        partes = [f.to_html(full_html=False, include_plotlyjs="cdn" if i == 0 else False)
                  for i, f in enumerate([fig_mensual(df), fig_categorias(df), fig_saldo(df)])]
        a.exportar.write_text("<html><meta charset='utf-8'><body><h1>Finanzas personales</h1>" + "".join(partes)
                              + "</body></html>", encoding="utf-8")
        print(f"Reporte en {a.exportar}")
        return 0
    from .app import crear_app  # pragma: no cover - levanta servidor
    # 127.0.0.1: el dashboard expone datos financieros, no se publica en la red.
    crear_app(df).run(host="127.0.0.1", port=a.puerto, debug=False)  # pragma: no cover
    return 0  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
