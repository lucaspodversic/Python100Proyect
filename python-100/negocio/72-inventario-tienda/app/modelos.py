"""Modelos ORM del inventario.

Decisiones:
- El stock se guarda en el producto (``stock``) para consultas rápidas, y cada
  cambio queda registrado en ``Movimiento`` (auditoría: quién, cuándo, cuánto).
- Precios en centavos enteros.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Rol(str, enum.Enum):
    """Roles: ``lector`` solo consulta, ``empleado`` mueve stock, ``admin`` gestiona todo."""

    LECTOR = "lector"
    EMPLEADO = "empleado"
    ADMIN = "admin"


class TipoMovimiento(str, enum.Enum):
    """Tipos de movimiento de stock."""

    ENTRADA = "entrada"   # compra recibida, devolución de cliente...
    SALIDA = "salida"     # venta, merma...
    AJUSTE = "ajuste"     # corrección tras inventario físico (fija el valor)


class EstadoOrden(str, enum.Enum):
    """Ciclo de vida de una orden de compra a proveedor."""

    PENDIENTE = "pendiente"
    RECIBIDA = "recibida"
    CANCELADA = "cancelada"


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class Usuario(Base):
    """Usuario del sistema. La contraseña se guarda como hash PBKDF2 con sal."""

    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(300))
    rol: Mapped[Rol] = mapped_column(Enum(Rol))


class Token(Base):
    """Token de sesión: se persiste su SHA-256, nunca el token en claro."""

    __tablename__ = "tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    usuario: Mapped["Usuario"] = relationship()


class Proveedor(Base):
    """Proveedor de productos."""

    __tablename__ = "proveedores"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True)
    email: Mapped[str] = mapped_column(String(200))
    telefono: Mapped[str] = mapped_column(String(40), default="")


class Producto(Base):
    """Producto del catálogo. El ``CheckConstraint`` impide stock negativo a nivel de BD."""

    __tablename__ = "productos"
    __table_args__ = (CheckConstraint("stock >= 0", name="stock_no_negativo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(200))
    precio_centavos: Mapped[int] = mapped_column(Integer)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    stock_minimo: Mapped[int] = mapped_column(Integer, default=0)
    proveedor_id: Mapped[int | None] = mapped_column(ForeignKey("proveedores.id"), nullable=True)

    proveedor: Mapped[Proveedor | None] = relationship()


class Movimiento(Base):
    """Registro inmutable de cada cambio de stock."""

    __tablename__ = "movimientos"

    id: Mapped[int] = mapped_column(primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    tipo: Mapped[TipoMovimiento] = mapped_column(Enum(TipoMovimiento))
    cantidad: Mapped[int] = mapped_column(Integer)
    stock_resultante: Mapped[int] = mapped_column(Integer)
    motivo: Mapped[str] = mapped_column(String(200), default="")
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)


class OrdenCompra(Base):
    """Orden de compra a un proveedor; al recibirse incrementa el stock."""

    __tablename__ = "ordenes"

    id: Mapped[int] = mapped_column(primary_key=True)
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("proveedores.id"))
    estado: Mapped[EstadoOrden] = mapped_column(Enum(EstadoOrden), default=EstadoOrden.PENDIENTE)
    creada: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)

    lineas: Mapped[list["LineaOrden"]] = relationship(cascade="all, delete-orphan")


class LineaOrden(Base):
    """Línea de una orden de compra (producto + cantidad)."""

    __tablename__ = "lineas_orden"

    id: Mapped[int] = mapped_column(primary_key=True)
    orden_id: Mapped[int] = mapped_column(ForeignKey("ordenes.id", ondelete="CASCADE"))
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"))
    cantidad: Mapped[int] = mapped_column(Integer)
