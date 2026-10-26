"""Modelos ORM del gestor de proyectos.

Los permisos son **por tablero** (``Miembro.permiso``), no globales: un mismo
usuario puede ser dueño de un tablero y solo lector en otro.

Las posiciones de listas y tarjetas son enteros contiguos 0..n-1 que se
renumeran al mover elementos (simple y sin huecos).
"""
from __future__ import annotations

import enum
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Rol(str, enum.Enum):
    """Rol global (todos los registrados son usuarios; los permisos van por tablero)."""

    USUARIO = "usuario"


class Permiso(str, enum.Enum):
    """Permiso dentro de un tablero, de menor a mayor."""

    LECTOR = "lector"     # solo ve
    EDITOR = "editor"     # crea/mueve tarjetas y listas
    DUENIO = "duenio"     # además gestiona miembros y borra el tablero


NIVEL = {Permiso.LECTOR: 1, Permiso.EDITOR: 2, Permiso.DUENIO: 3}


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


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


class Tablero(Base):
    __tablename__ = "tableros"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))

    listas: Mapped[list["Lista"]] = relationship(order_by="Lista.posicion", cascade="all, delete-orphan")
    miembros: Mapped[list["Miembro"]] = relationship(cascade="all, delete-orphan")


class Miembro(Base):
    """Pertenencia de un usuario a un tablero con un permiso."""

    __tablename__ = "miembros"
    __table_args__ = (UniqueConstraint("tablero_id", "usuario_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tablero_id: Mapped[int] = mapped_column(ForeignKey("tableros.id", ondelete="CASCADE"))
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    permiso: Mapped[Permiso] = mapped_column(Enum(Permiso))


class Lista(Base):
    """Columna del tablero (p. ej. "Por hacer", "En curso", "Hecho")."""

    __tablename__ = "listas"

    id: Mapped[int] = mapped_column(primary_key=True)
    tablero_id: Mapped[int] = mapped_column(ForeignKey("tableros.id", ondelete="CASCADE"))
    nombre: Mapped[str] = mapped_column(String(120))
    posicion: Mapped[int] = mapped_column(Integer)

    tarjetas: Mapped[list["Tarjeta"]] = relationship(order_by="Tarjeta.posicion", cascade="all, delete-orphan",
                                                     back_populates="lista")


class Tarjeta(Base):
    """Tarea dentro de una lista."""

    __tablename__ = "tarjetas"

    id: Mapped[int] = mapped_column(primary_key=True)
    lista_id: Mapped[int] = mapped_column(ForeignKey("listas.id", ondelete="CASCADE"))
    titulo: Mapped[str] = mapped_column(String(200))
    descripcion: Mapped[str] = mapped_column(Text, default="")
    posicion: Mapped[int] = mapped_column(Integer)
    vence: Mapped[date | None] = mapped_column(Date, nullable=True)
    asignado_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    etiquetas: Mapped[str] = mapped_column(String(300), default="")  # separadas por coma

    lista: Mapped[Lista] = relationship(back_populates="tarjetas")


class Actividad(Base):
    """Registro de auditoría de lo que pasa en el tablero."""

    __tablename__ = "actividad"

    id: Mapped[int] = mapped_column(primary_key=True)
    tablero_id: Mapped[int] = mapped_column(ForeignKey("tableros.id", ondelete="CASCADE"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    texto: Mapped[str] = mapped_column(String(300))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=_ahora)
