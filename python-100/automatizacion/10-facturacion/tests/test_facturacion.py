"""Tests: PDFs generados con fpdf2 en tmp_path, contabilidad SQLite en memoria."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest

from facturacion import (Procesador, SQLiteContabilidad, extraer_datos, generar_factura_pdf, parsear_importe,
                         texto_pdf, validar)
from facturacion.cli import main
from facturacion.procesador import exportar_revision

# Fecha fija: facturas de feb/mar 2025 son pasadas; 01/05/2025 es futura.
HOY = dt.date(2025, 4, 1)


@pytest.mark.parametrize("entrada,esperado", [
    # Formatos AR y US dan el mismo valor; "$ 99" sin decimales → 99.00; "1234.5" → 1234.50;
    # "12.345.678,9": la última coma con 1 dígito es decimal → 12345678.90; "" → None.
    ("1.234,56", "1234.56"), ("1,234.56", "1234.56"), ("$ 99", "99.00"), ("1234.5", "1234.50"),
    ("12.345.678,9", "12345678.90"), ("€ 0,99", "0.99"), ("", None),
])
def test_parsear_importe(entrada: str, esperado: str | None) -> None:
    r = parsear_importe(entrada)
    assert (str(r) if r is not None else None) == esperado


def test_extraer_de_texto_plano() -> None:
    texto = """Invoice # INV-88
    Vendor: ACME Corp
    Tax ID: 12-3456789
    Date: 2025-02-10
    Subtotal: USD 1,000.00
    VAT (21%): USD 210.00
    TOTAL: USD 1,210.00"""
    # Factura en inglés: número tras "Invoice #", fecha ISO, moneda USD por "USD";
    # 1000 + 210 = 1210 → validación sin errores.
    d = extraer_datos(texto)
    assert (d.numero, d.proveedor, d.fecha, d.moneda) == ("INV-88", "ACME Corp", dt.date(2025, 2, 10), "USD")
    assert (d.subtotal, d.iva, d.total) == (Decimal("1000.00"), Decimal("210.00"), Decimal("1210.00"))
    assert validar(d, HOY) == []


def test_pdf_real_ida_y_vuelta(tmp_path: Path) -> None:
    ruta = generar_factura_pdf(tmp_path / "f.pdf", proveedor="Papelera Sur SRL", numero="A-0001-00000123",
                               fecha="15/03/2025", items=[("Resmas A4", 10, Decimal("5200.00")),
                                                          ("Toner", 2, Decimal("31500.50"))])
    # Números esperados: 10 × 5200 + 2 × 31500.50 = 52000 + 63001 = 115001.00;
    # IVA 21% = 24150.21; total = 139151.21. Ida y vuelta: generar PDF → extraer texto → parsear.
    d = extraer_datos(texto_pdf(ruta))
    assert d.numero == "A-0001-00000123" and d.proveedor == "Papelera Sur SRL"
    assert d.id_fiscal == "30-71234567-9" and d.fecha == dt.date(2025, 3, 15)
    assert d.subtotal == Decimal("115001.00") and d.iva == Decimal("24150.21") and d.total == Decimal("139151.21")
    assert validar(d, HOY) == []


def test_validaciones() -> None:
    # 01/05/2025 > HOY → "fecha futura"; 100 + 21 = 121 ≠ 150 → error de suma.
    d = extraer_datos("Factura N° 1\nProveedor: X\nFecha: 01/05/2025\nSubtotal: 100\nIVA: 21\nTotal: 150")
    errores = validar(d, HOY)
    assert "fecha futura" in errores and any("!= total" in e for e in errores)
    # Texto sin datos: faltan los 4 campos obligatorios (y no hay importes para comparar).
    assert set(validar(extraer_datos("nada útil"), HOY)) == {"falta numero", "falta fecha", "falta proveedor",
                                                             "falta total"}


def test_procesar_carpeta_contabiliza_y_separa(tmp_path: Path) -> None:
    # Lote de 5 archivos:
    #   a.pdf: 1000 + 21% = 1210 → registrada
    #   b.pdf: 40 USD con IVA 0 → registrada (sin línea de IVA)
    #   c.pdf: mismo proveedor y número que a.pdf → duplicada
    #   d.pdf: total forzado 5 ≠ 1210 → revisión
    #   e.pdf: no es un PDF → revisión por error de lectura
    items = [("Servicio", 1, Decimal("1000"))]
    generar_factura_pdf(tmp_path / "a.pdf", proveedor="Uno SA", numero="A-1", fecha="01/03/2025", items=items)
    generar_factura_pdf(tmp_path / "b.pdf", proveedor="Dos SA", numero="B-7", fecha="02/03/2025",
                        items=[("VPS", 1, Decimal("40"))], estilo="us", simbolo="USD", tasa_iva=Decimal("0"))
    generar_factura_pdf(tmp_path / "c.pdf", proveedor="Uno SA", numero="A-1", fecha="01/03/2025", items=items)
    generar_factura_pdf(tmp_path / "d.pdf", proveedor="Mal SA", numero="X-1", fecha="01/03/2025", items=items,
                        total_forzado=Decimal("5"))
    (tmp_path / "e.pdf").write_bytes(b"no soy un pdf")
    conta = SQLiteContabilidad()
    r = Procesador(conta, hoy=HOY, mover=True).procesar_carpeta(tmp_path)
    assert r.registradas == ["a.pdf", "b.pdf"] and r.duplicadas == ["c.pdf"]
    assert set(r.revision) == {"d.pdf", "e.pdf"} and "error leyendo PDF" in r.revision["e.pdf"][0]
    assert sorted(p.name for p in (tmp_path / "procesadas").iterdir()) == ["a.pdf", "b.pdf"]
    # revision/ recibe c (duplicada), d y e.
    assert len(list((tmp_path / "revision").iterdir())) == 3
    # Partida doble: la suma de saldos es 0.
    # Saldos: Gastos 1000 + 40 = 1040; IVA 210 (sólo de a.pdf); Proveedores −(1210 + 40) = −1250.
    bal = conta.balance()
    assert bal == {"Gastos": Decimal("1040.00"), "IVA crédito fiscal": Decimal("210.00"),
                   "Proveedores": Decimal("-1250.00")}
    assert sum(bal.values()) == 0
    moneda = conta.db.execute("SELECT moneda FROM facturas WHERE numero='B-7'").fetchone()[0]
    assert moneda == "USD"
    exportar_revision(r, tmp_path / "rev.csv")
    assert "duplicada" in (tmp_path / "rev.csv").read_text(encoding="utf-8-sig")


def test_cli_demo_y_procesar(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["demo", str(tmp_path / "in")]) == 0
    # De los 3 PDFs demo, f1 y f2 se registran y f3 (total 999 incorrecto) va a revisión.
    assert main(["procesar", str(tmp_path / "in"), "--db", str(tmp_path / "c.db")]) == 0
    out = capsys.readouterr().out
    assert "Registradas: 2" in out and "A revisar: 1" in out
