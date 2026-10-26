"""Modelos ORM de vuelos y reservas.

Todas las fechas se guardan como UTC *naive* (SQLite no guarda zona horaria);
la convención es documentada y consistente en todo el proyecto.

Clave del diseño anti doble-venta: ``AsientoOcupado`` tiene clave primaria
compuesta ``(vuelo_id, asiento)``. Es un "candado físico": la base de datos
rechaza con ``IntegrityError`` un segundo intento de ocupar el mismo asiento,
aunque dos peticiones lleguen a la vez.
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Rol(str, enum.Enum):
    CLIENTE = "cliente"
    ADMIN = "admin"


class EstadoReserva(str, enum.Enum):
    RETENIDA = "retenida"        # asiento bloqueado unos minutos, pendiente de pago
    CONFIRMADA = "confirmada"
    CANCELADA = "cancelada"
    EXPIRADA = "expirada"        # la retención venció sin confirmarse


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


class Vuelo(Base):
    """Vuelo programado con una cabina de ``filas`` × ``columnas``."""

    __tablename__ = "vuelos"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10))
    origen: Mapped[str] = mapped_column(String(3), index=True)   # código IATA, p. ej. EZE
    destino: Mapped[str] = mapped_column(String(3), index=True)
    salida: Mapped[datetime] = mapped_column(DateTime)
    filas: Mapped[int] = mapped_column(Integer)
    columnas: Mapped[str] = mapped_column(String(10))            # p. ej. "ABCDEF"
    precio_base_centavos: Mapped[int] = mapped_column(Integer)

    @property
    def capacidad(self) -> int:
        return self.filas * len(self.columnas)


class Reserva(Base):
    """Reserva de un asiento identificada por un PNR (localizador de 6 caracteres)."""

    __tablename__ = "reservas"

    id: Mapped[int] = mapped_column(primary_key=True)
    pnr: Mapped[str] = mapped_column(String(6), unique=True, index=True)
    vuelo_id: Mapped[int] = mapped_column(ForeignKey("vuelos.id"))
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    asiento: Mapped[str] = mapped_column(String(4))
    pasajero: Mapped[str] = mapped_column(String(120))
    precio_centavos: Mapped[int] = mapped_column(Integer)
    estado: Mapped[EstadoReserva] = mapped_column(Enum(EstadoReserva))
    expira_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AsientoOcupado(Base):
    """Candado de asiento: existe una fila mientras el asiento está retenido o vendido."""

    __tablename__ = "asientos_ocupados"

    vuelo_id: Mapped[int] = mapped_column(ForeignKey("vuelos.id"), primary_key=True)
    asiento: Mapped[str] = mapped_column(String(4), primary_key=True)
    reserva_id: Mapped[int] = mapped_column(ForeignKey("reservas.id", ondelete="CASCADE"), unique=True)

    reserva: Mapped[Reserva] = relationship()
