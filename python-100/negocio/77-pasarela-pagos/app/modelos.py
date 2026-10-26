"""Modelos ORM de la pasarela de pagos.

Importes en **centavos enteros**: nunca ``float`` para dinero.
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Rol(str, enum.Enum):
    COMERCIO = "comercio"
    ADMIN = "admin"


class EstadoPago(str, enum.Enum):
    APROBADO = "aprobado"
    RECHAZADO = "rechazado"
    REEMBOLSADO_PARCIAL = "reembolsado_parcial"
    REEMBOLSADO = "reembolsado"


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


class ConfigWebhook(Base):
    """URL y secreto de firma de webhooks de un comercio."""

    __tablename__ = "config_webhooks"

    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), primary_key=True)
    url: Mapped[str] = mapped_column(String(500))
    secreto: Mapped[str] = mapped_column(String(100))  # se necesita en claro para firmar


class Pago(Base):
    __tablename__ = "pagos"
    __table_args__ = (
        CheckConstraint("monto_centavos > 0"),
        CheckConstraint("reembolsado_centavos >= 0 AND reembolsado_centavos <= monto_centavos"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    publico: Mapped[str] = mapped_column(String(40), unique=True)  # id público "pay_..."
    comercio_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    monto_centavos: Mapped[int] = mapped_column(Integer)
    moneda: Mapped[str] = mapped_column(String(3))
    estado: Mapped[EstadoPago] = mapped_column(Enum(EstadoPago))
    motivo_rechazo: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ultimos4: Mapped[str] = mapped_column(String(4))
    marca: Mapped[str] = mapped_column(String(20))
    reembolsado_centavos: Mapped[int] = mapped_column(Integer, default=0)
    descripcion: Mapped[str] = mapped_column(String(300), default="")
    creado: Mapped[datetime] = mapped_column(DateTime)


class Reembolso(Base):
    __tablename__ = "reembolsos"
    __table_args__ = (CheckConstraint("monto_centavos > 0"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    publico: Mapped[str] = mapped_column(String(40), unique=True)
    pago_id: Mapped[int] = mapped_column(ForeignKey("pagos.id"), index=True)
    monto_centavos: Mapped[int] = mapped_column(Integer)
    motivo: Mapped[str] = mapped_column(String(200), default="")
    creado: Mapped[datetime] = mapped_column(DateTime)


class ClaveIdempotencia(Base):
    """Respuesta guardada para una ``Idempotency-Key`` de un comercio.

    La restricción única (comercio, clave) garantiza que dos peticiones
    simultáneas con la misma clave no ejecuten la operación dos veces.
    """

    __tablename__ = "claves_idempotencia"
    __table_args__ = (UniqueConstraint("comercio_id", "clave"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    comercio_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    clave: Mapped[str] = mapped_column(String(100))
    huella: Mapped[str] = mapped_column(String(64))  # SHA-256 de ruta + cuerpo
    codigo: Mapped[int] = mapped_column(Integer)
    respuesta: Mapped[str] = mapped_column(Text)  # JSON
    creado: Mapped[datetime] = mapped_column(DateTime)


class Evento(Base):
    """Evento de webhook pendiente o entregado (patrón *outbox*)."""

    __tablename__ = "eventos"

    id: Mapped[int] = mapped_column(primary_key=True)
    publico: Mapped[str] = mapped_column(String(40), unique=True)
    comercio_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(50))
    cuerpo: Mapped[str] = mapped_column(Text)
    intentos: Mapped[int] = mapped_column(Integer, default=0)
    entregado: Mapped[bool] = mapped_column(default=False)
    ultimo_error: Mapped[str | None] = mapped_column(String(200), nullable=True)
