"""Modelos ORM de la mesa de ayuda."""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Rol(str, enum.Enum):
    """Cliente abre tickets y ve solo los suyos; agente los atiende; admin puede todo."""
    CLIENTE = "cliente"
    AGENTE = "agente"
    ADMIN = "admin"


class Prioridad(str, enum.Enum):
    """Determina los plazos de SLA (ver servicio.SLA)."""
    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"
    URGENTE = "urgente"


class Estado(str, enum.Enum):
    """Estados del ciclo de vida del ticket; 'cerrado' es final."""
    ABIERTO = "abierto"
    EN_PROGRESO = "en_progreso"
    ESPERANDO_CLIENTE = "esperando_cliente"
    RESUELTO = "resuelto"
    CERRADO = "cerrado"


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


class Ticket(Base):
    """Ticket: cliente, agente asignado (puede ser nulo), prioridad, estado, vencimientos de
    SLA calculados al crearlo, primera respuesta y fecha de resolución (para el plazo de
    reapertura). Los comentarios y cambios de estado quedan en tablas aparte como
    historial.
    """
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    asunto: Mapped[str] = mapped_column(String(200))
    descripcion: Mapped[str] = mapped_column(Text)
    prioridad: Mapped[Prioridad] = mapped_column(Enum(Prioridad))
    estado: Mapped[Estado] = mapped_column(Enum(Estado), default=Estado.ABIERTO, index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    agente_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True, index=True)
    creado: Mapped[datetime] = mapped_column(DateTime)
    # Plazos SLA calculados al crear (y recalculados si cambia la prioridad).
    vence_respuesta: Mapped[datetime] = mapped_column(DateTime)
    vence_resolucion: Mapped[datetime] = mapped_column(DateTime)
    primera_respuesta: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resuelto_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    comentarios: Mapped[list["Comentario"]] = relationship(order_by="Comentario.id", cascade="all, delete-orphan")
    historial: Mapped[list["Cambio"]] = relationship(order_by="Cambio.id", cascade="all, delete-orphan")


class Comentario(Base):
    """Comentario público o **nota interna** (invisible para el cliente)."""

    __tablename__ = "comentarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"))
    autor_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    texto: Mapped[str] = mapped_column(Text)
    interno: Mapped[bool] = mapped_column(Boolean, default=False)
    fecha: Mapped[datetime] = mapped_column(DateTime)


class Cambio(Base):
    """Historial de transiciones de estado (auditoría)."""

    __tablename__ = "cambios"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"))
    autor_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    de: Mapped[str] = mapped_column(String(30))
    a: Mapped[str] = mapped_column(String(30))
    fecha: Mapped[datetime] = mapped_column(DateTime)
