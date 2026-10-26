"""Modelos ORM del CMS."""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Rol(str, enum.Enum):
    """Autor escribe y envía a revisión; editor revisa, publica y archiva; admin además
    gestiona roles.
    """
    AUTOR = "autor"     # escribe y envía a revisión sus artículos
    EDITOR = "editor"   # revisa, publica, archiva cualquier artículo
    ADMIN = "admin"     # además gestiona roles


class Estado(str, enum.Enum):
    """borrador → en_revision → publicado → archivado (con rechazo de vuelta a borrador)."""
    BORRADOR = "borrador"
    EN_REVISION = "en_revision"
    PUBLICADO = "publicado"
    ARCHIVADO = "archivado"


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


class Articulo(Base):
    """Artículo: slug único, título, cuerpo en Markdown, etiquetas separadas por comas, estado,
    ``version`` (para el bloqueo optimista) y ``publicar_en`` (publicación programada).
    """
    __tablename__ = "articulos"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(220), unique=True, index=True)
    titulo: Mapped[str] = mapped_column(String(200))
    cuerpo: Mapped[str] = mapped_column(Text)
    etiquetas: Mapped[str] = mapped_column(String(300), default="")
    autor_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    estado: Mapped[Estado] = mapped_column(Enum(Estado), default=Estado.BORRADOR, index=True)
    publicar_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # publicación programada
    # Bloqueo optimista: cada edición incrementa la versión.
    version: Mapped[int] = mapped_column(Integer, default=1)

    revisiones: Mapped[list["Revision"]] = relationship(order_by="Revision.numero", cascade="all, delete-orphan")


class Revision(Base):
    """Instantánea de cada versión guardada (permite ver historial y restaurar)."""

    __tablename__ = "revisiones"
    __table_args__ = (UniqueConstraint("articulo_id", "numero"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    articulo_id: Mapped[int] = mapped_column(ForeignKey("articulos.id", ondelete="CASCADE"))
    numero: Mapped[int] = mapped_column(Integer)
    titulo: Mapped[str] = mapped_column(String(200))
    cuerpo: Mapped[str] = mapped_column(Text)
    autor_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime)


class Medio(Base):
    """Imagen subida. El archivo se guarda con un nombre aleatorio, nunca el del cliente."""

    __tablename__ = "medios"

    id: Mapped[int] = mapped_column(primary_key=True)
    archivo: Mapped[str] = mapped_column(String(100), unique=True)
    nombre_original: Mapped[str] = mapped_column(String(200))
    tipo: Mapped[str] = mapped_column(String(50))
    bytes: Mapped[int] = mapped_column(Integer)
    subido_por: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
