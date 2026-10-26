"""Modelos ORM (tablas) del sistema de reservas.

Los importes se guardan en **centavos enteros** para evitar errores de redondeo
de los números de punto flotante.
"""
from __future__ import annotations

import enum
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Rol(str, enum.Enum):
    """Roles de usuario: el administrador gestiona habitaciones y ve todo."""

    ADMIN = "admin"
    CLIENTE = "cliente"


class EstadoReserva(str, enum.Enum):
    """Estados posibles de una reserva."""

    CONFIRMADA = "confirmada"
    CANCELADA = "cancelada"


def _ahora() -> datetime:
    """Fecha y hora actual en UTC (para columnas de auditoría)."""
    return datetime.now(timezone.utc)


class Usuario(Base):
    """Usuario del sistema (cliente o administrador)."""

    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    # Nunca guardamos la contraseña en claro: solo su hash PBKDF2 con sal.
    password_hash: Mapped[str] = mapped_column(String(300))
    rol: Mapped[Rol] = mapped_column(Enum(Rol), default=Rol.CLIENTE)


class Token(Base):
    """Token de sesión. Se guarda el SHA-256 del token, no el token en sí."""

    __tablename__ = "tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    creado: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)

    usuario: Mapped[Usuario] = relationship()


class Habitacion(Base):
    """Habitación del hotel."""

    __tablename__ = "habitaciones"

    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[str] = mapped_column(String(10), unique=True)
    tipo: Mapped[str] = mapped_column(String(30))  # simple, doble, suite...
    capacidad: Mapped[int] = mapped_column(Integer)
    precio_noche_centavos: Mapped[int] = mapped_column(Integer)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)


class Reserva(Base):
    """Reserva de una habitación entre ``entrada`` (incluida) y ``salida`` (excluida).

    Usar intervalos semiabiertos ``[entrada, salida)`` permite que un huésped
    salga el mismo día que entra el siguiente sin que cuente como solapamiento.
    """

    __tablename__ = "reservas"

    id: Mapped[int] = mapped_column(primary_key=True)
    habitacion_id: Mapped[int] = mapped_column(ForeignKey("habitaciones.id"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    entrada: Mapped[date] = mapped_column(Date)
    salida: Mapped[date] = mapped_column(Date)
    huespedes: Mapped[int] = mapped_column(Integer)
    total_centavos: Mapped[int] = mapped_column(Integer)
    estado: Mapped[EstadoReserva] = mapped_column(
        Enum(EstadoReserva), default=EstadoReserva.CONFIRMADA
    )
    creada: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)

    habitacion: Mapped[Habitacion] = relationship()
