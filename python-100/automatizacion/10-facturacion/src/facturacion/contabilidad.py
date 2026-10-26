"""Interfaz contable + implementación SQLite con partida doble.

Asiento de una factura de compra:

    Debe  Gastos (subtotal)          Haber  Proveedores (total)
    Debe  IVA crédito fiscal (iva)

Para integrar un sistema real (Xero, QuickBooks, Odoo, Contabilium…) basta con
implementar ``SistemaContable`` con su API.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from typing import Protocol

from .extractor import DatosFactura


# Sólo dos operaciones: detectar duplicados y registrar. Es lo mínimo que hay que implementar
# para conectar otro sistema contable.
class SistemaContable(Protocol):
    def existe(self, proveedor: str, numero: str) -> bool: ...

    def registrar(self, d: DatosFactura, archivo: str) -> int: ...


class SQLiteContabilidad:
    # Importes guardados como TEXT (str de Decimal) para no perder precisión: REAL sería float.
    # UNIQUE(proveedor, numero) es la defensa final contra duplicados a nivel de base.
    def __init__(self, ruta: str = ":memory:") -> None:
        self.db = sqlite3.connect(ruta)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS facturas (
                id INTEGER PRIMARY KEY, proveedor TEXT, id_fiscal TEXT, numero TEXT, fecha TEXT,
                subtotal TEXT, iva TEXT, total TEXT, moneda TEXT, archivo TEXT,
                UNIQUE(proveedor, numero));
            CREATE TABLE IF NOT EXISTS asientos (
                id INTEGER PRIMARY KEY, factura_id INTEGER REFERENCES facturas(id),
                cuenta TEXT, debe TEXT, haber TEXT);
        """)

    def existe(self, proveedor: str, numero: str) -> bool:
        return self.db.execute("SELECT 1 FROM facturas WHERE proveedor=? AND numero=?",
                               (proveedor, numero)).fetchone() is not None

    def registrar(self, d: DatosFactura, archivo: str) -> int:
        """Inserta factura + asiento en una transacción. Devuelve el id de factura."""
        # Precondición: el procesador sólo llama a registrar con datos ya validados.
        assert d.total is not None and d.proveedor and d.numero and d.fecha
        iva = d.iva or Decimal("0")
        # Si la factura no informa subtotal, se deduce como total − IVA para que el asiento balancee.
        subtotal = d.subtotal if d.subtotal is not None else d.total - iva
        with self.db:  # commit/rollback automático
            cur = self.db.execute(
                "INSERT INTO facturas (proveedor,id_fiscal,numero,fecha,subtotal,iva,total,moneda,archivo)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (d.proveedor, d.id_fiscal, d.numero, d.fecha.isoformat(), str(subtotal), str(iva), str(d.total),
                 d.moneda, archivo))
            fid = int(cur.lastrowid or 0)
            # Partida doble: Debe = Gastos + IVA; Haber = Proveedores. Debe − Haber = 0.
            lineas = [("Gastos", subtotal, Decimal(0)), ("Proveedores", Decimal(0), d.total)]
            # Sin IVA (exento o tasa 0) no se genera una línea en cero.
            if iva:
                lineas.insert(1, ("IVA crédito fiscal", iva, Decimal(0)))
            self.db.executemany("INSERT INTO asientos (factura_id,cuenta,debe,haber) VALUES (?,?,?,?)",
                                [(fid, c, str(de), str(ha)) for c, de, ha in lineas])
        return fid

    def balance(self) -> dict[str, Decimal]:
        """Saldo (debe - haber) por cuenta. Suma 0 si la partida doble está bien."""
        saldos: dict[str, Decimal] = {}
        for cuenta, debe, haber in self.db.execute("SELECT cuenta, debe, haber FROM asientos"):
            # Saldo deudor positivo, acreedor negativo (Proveedores queda negativo).
            saldos[cuenta] = saldos.get(cuenta, Decimal(0)) + Decimal(debe) - Decimal(haber)
        return saldos
