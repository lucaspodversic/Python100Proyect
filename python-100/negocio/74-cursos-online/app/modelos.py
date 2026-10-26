"""Modelos ORM de la plataforma de cursos."""
from __future__ import annotations

import enum

from sqlalchemy import JSON, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Rol(str, enum.Enum):
    """``alumno`` cursa, ``profesor`` crea cursos, ``admin`` asigna roles."""

    ALUMNO = "alumno"
    PROFESOR = "profesor"
    ADMIN = "admin"


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


class Curso(Base):
    """Curso creado por un profesor. Solo los publicados admiten inscripciones."""

    __tablename__ = "cursos"

    id: Mapped[int] = mapped_column(primary_key=True)
    titulo: Mapped[str] = mapped_column(String(200))
    descripcion: Mapped[str] = mapped_column(Text, default="")
    profesor_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    publicado: Mapped[bool] = mapped_column(default=False)

    lecciones: Mapped[list["Leccion"]] = relationship(order_by="Leccion.orden", cascade="all, delete-orphan")
    examen: Mapped["Examen | None"] = relationship(uselist=False, cascade="all, delete-orphan")


class Leccion(Base):
    """Lección de un curso; ``orden`` define la secuencia."""

    __tablename__ = "lecciones"
    __table_args__ = (UniqueConstraint("curso_id", "orden"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    curso_id: Mapped[int] = mapped_column(ForeignKey("cursos.id", ondelete="CASCADE"))
    orden: Mapped[int] = mapped_column(Integer)
    titulo: Mapped[str] = mapped_column(String(200))
    contenido: Mapped[str] = mapped_column(Text)


class Examen(Base):
    """Examen final de opción múltiple.

    ``preguntas`` es una lista JSON de ``{"enunciado", "opciones", "correcta"}``.
    El índice ``correcta`` nunca se envía al alumno.
    """

    __tablename__ = "examenes"

    id: Mapped[int] = mapped_column(primary_key=True)
    curso_id: Mapped[int] = mapped_column(ForeignKey("cursos.id", ondelete="CASCADE"), unique=True)
    preguntas: Mapped[list] = mapped_column(JSON)
    nota_aprobacion: Mapped[int] = mapped_column(Integer, default=60)  # porcentaje
    max_intentos: Mapped[int] = mapped_column(Integer, default=3)


class Inscripcion(Base):
    """Alumno inscripto en un curso (una sola vez)."""

    __tablename__ = "inscripciones"
    __table_args__ = (UniqueConstraint("curso_id", "alumno_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    curso_id: Mapped[int] = mapped_column(ForeignKey("cursos.id"))
    alumno_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))


class LeccionCompletada(Base):
    """Marca de lección completada (idempotente por la restricción única)."""

    __tablename__ = "lecciones_completadas"
    __table_args__ = (UniqueConstraint("leccion_id", "alumno_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    leccion_id: Mapped[int] = mapped_column(ForeignKey("lecciones.id", ondelete="CASCADE"))
    alumno_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))


class Intento(Base):
    """Intento de examen con su nota (0-100)."""

    __tablename__ = "intentos"

    id: Mapped[int] = mapped_column(primary_key=True)
    examen_id: Mapped[int] = mapped_column(ForeignKey("examenes.id", ondelete="CASCADE"))
    alumno_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    respuestas: Mapped[list] = mapped_column(JSON)
    nota: Mapped[int] = mapped_column(Integer)
    aprobado: Mapped[bool] = mapped_column()
