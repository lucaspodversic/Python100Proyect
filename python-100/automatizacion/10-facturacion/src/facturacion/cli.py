"""CLI::

    facturacion procesar ./bandeja --db contabilidad.db [--mover] [--revision revision.csv]
    facturacion demo ./bandeja      # genera 3 PDFs de ejemplo
"""

from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path

from .contabilidad import SQLiteContabilidad
from .generador import generar_factura_pdf
from .procesador import Procesador, exportar_revision


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="facturacion", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    # Dos subcomandos: "procesar" (uso real) y "demo" (genera PDFs de ejemplo para probar).
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("procesar")
    p.add_argument("carpeta", type=Path)
    p.add_argument("--db", default="contabilidad.db")
    # --mover separa físicamente en procesadas/ y revision/ para no reprocesar en la próxima corrida.
    p.add_argument("--mover", action="store_true")
    p.add_argument("--revision", type=Path)
    d = sub.add_parser("demo")
    d.add_argument("carpeta", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "demo":
        a.carpeta.mkdir(parents=True, exist_ok=True)
        # Tres casos demo: f1 válida en formato argentino; f2 en dólares con formato US (1,234.56);
        # f3 con total forzado incorrecto (999 ≠ 100 + 21) → debe ir a revisión.
        generar_factura_pdf(a.carpeta / "f1.pdf", proveedor="Papelera Sur SRL", numero="A-0001-00000123",
                            fecha="15/03/2025", items=[("Resmas A4", 10, Decimal("5200.00"))])
        generar_factura_pdf(a.carpeta / "f2.pdf", proveedor="Cloud Hosting Inc", numero="INV-2025-77",
                            fecha="01/03/2025", items=[("VPS", 1, Decimal("40.00"))], estilo="us", simbolo="USD")
        generar_factura_pdf(a.carpeta / "f3.pdf", proveedor="Error SA", numero="B-1", fecha="02/03/2025",
                            items=[("x", 1, Decimal("100"))], total_forzado=Decimal("999"))
        print(f"3 facturas de ejemplo en {a.carpeta}")
        return 0
    conta = SQLiteContabilidad(a.db)
    r = Procesador(conta, mover=a.mover).procesar_carpeta(a.carpeta)
    print(f"Registradas: {len(r.registradas)} | Duplicadas: {len(r.duplicadas)} | A revisar: {len(r.revision)}")
    # Detalle de cada factura a revisar, con todos sus problemas en una línea.
    for archivo, probs in r.revision.items():
        print(f"  ⚠ {archivo}: {'; '.join(probs)}")
    if a.revision:
        exportar_revision(r, a.revision)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
