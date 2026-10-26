"""Modelos ORM de encuestas.

Las respuestas son **anónimas**: ``Respuesta`` no guarda quién respondió. El
código de invitación solo se marca como usado, sin vincularse a la respuesta.
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Rol(str, enum.Enum):
    CREADOR = "creador"
    ADMIN = "admin"


class TipoPregunta(str, enum.Enum):
    UNICA = "unica"          # una opción
    MULTIPLE = "multiple"    # varias opciones
    ESCALA = "escala"        # entero 1..5
    TEXTO = "texto"          # texto libre


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


class Encuesta(Base):
    __tablename__ = "encuestas"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(40), unique=True)  # enlace público opaco
    titulo: Mapped[str] = mapped_column(String(200))
    creador_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    abierta: Mapped[bool] = mapped_column(Boolean, default=True)
    requiere_codigo: Mapped[bool] = mapped_column(Boolean, default=False)
    cierra_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    preguntas: Mapped[list["Pregunta"]] = relationship(order_by="Pregunta.orden", cascade="all, delete-orphan")


class Pregunta(Base):
    __tablename__ = "preguntas"
    __table_args__ = (UniqueConstraint("encuesta_id", "orden"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    encuesta_id: Mapped[int] = mapped_column(ForeignKey("encuestas.id", ondelete="CASCADE"))
    orden: Mapped[int] = mapped_column(Integer)
    texto: Mapped[str] = mapped_column(String(500))
    tipo: Mapped[TipoPregunta] = mapped_column(Enum(TipoPregunta))
    opciones: Mapped[list[str]] = mapped_column(JSON, default=list)
    obligatoria: Mapped[bool] = mapped_column(Boolean, default=True)


class Codigo(Base):
    """Código de invitación de un solo uso."""

    __tablename__ = "codigos"

    id: Mapped[int] = mapped_column(primary_key=True)
    encuesta_id: Mapped[int] = mapped_column(ForeignKey("encuestas.id", ondelete="CASCADE"), index=True)
    codigo_hash: Mapped[str] = mapped_column(String(64), unique=True)  # SHA-256, nunca en claro
    usado: Mapped[bool] = mapped_column(Boolean, default=False)


class Respuesta(Base):
    """Una respuesta completa (anónima). ``valores`` mapea id de pregunta → valor."""

    __tablename__ = "respuestas"

    id: Mapped[int] = mapped_column(primary_key=True)
    encuesta_id: Mapped[int] = mapped_column(ForeignKey("encuestas.id", ondelete="CASCADE"), index=True)
    valores: Mapped[dict] = mapped_column(JSON)
