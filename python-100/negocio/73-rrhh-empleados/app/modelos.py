"""Modelos ORM de RRHH.

- ``Empleado`` es el legajo; puede vincularse a un ``Usuario`` para que el
  empleado consulte sus datos y pida ausencias.
- ``Ausencia`` usa fechas inclusivas ``[desde, hasta]`` (días calendario).
- ``Nomina`` guarda montos en centavos y es única por (empleado, período).
"""
from __future__ import annotations

import enum
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Rol(str, enum.Enum):
    """``empleado`` ve lo suyo; ``rrhh`` gestiona; ``admin`` además asigna roles."""

    EMPLEADO = "empleado"
    RRHH = "rrhh"
    ADMIN = "admin"


class TipoAusencia(str, enum.Enum):
    VACACIONES = "vacaciones"   # consume saldo anual, con goce de sueldo
    ENFERMEDAD = "enfermedad"   # con goce de sueldo
    SIN_GOCE = "sin_goce"       # se descuenta de la nómina


class EstadoAusencia(str, enum.Enum):
    SOLICITADA = "solicitada"
    APROBADA = "aprobada"
    RECHAZADA = "rechazada"


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


class Empleado(Base):
    """Legajo de un empleado."""

    __tablename__ = "empleados"

    id: Mapped[int] = mapped_column(primary_key=True)
    legajo: Mapped[str] = mapped_column(String(20), unique=True)
    nombre: Mapped[str] = mapped_column(String(120))
    departamento: Mapped[str] = mapped_column(String(60))
    puesto: Mapped[str] = mapped_column(String(60))
    fecha_ingreso: Mapped[date] = mapped_column(Date)
    salario_bruto_centavos: Mapped[int] = mapped_column(Integer)
    dias_vacaciones_anuales: Mapped[int] = mapped_column(Integer, default=14)
    activo: Mapped[bool] = mapped_column(default=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), unique=True, nullable=True)


class Ausencia(Base):
    """Solicitud de ausencia con su estado de aprobación."""

    __tablename__ = "ausencias"

    id: Mapped[int] = mapped_column(primary_key=True)
    empleado_id: Mapped[int] = mapped_column(ForeignKey("empleados.id"), index=True)
    tipo: Mapped[TipoAusencia] = mapped_column(Enum(TipoAusencia))
    desde: Mapped[date] = mapped_column(Date)
    hasta: Mapped[date] = mapped_column(Date)
    estado: Mapped[EstadoAusencia] = mapped_column(Enum(EstadoAusencia), default=EstadoAusencia.SOLICITADA)
    resuelta_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)

    empleado: Mapped[Empleado] = relationship()

    @property
    def dias(self) -> int:
        """Cantidad de días calendario (ambos extremos incluidos)."""
        return (self.hasta - self.desde).days + 1


class Nomina(Base):
    """Liquidación mensual. La restricción única evita liquidar dos veces el mismo mes."""

    __tablename__ = "nominas"
    __table_args__ = (UniqueConstraint("empleado_id", "periodo", name="una_nomina_por_mes"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    empleado_id: Mapped[int] = mapped_column(ForeignKey("empleados.id"), index=True)
    periodo: Mapped[str] = mapped_column(String(7))  # "AAAA-MM"
    bruto_centavos: Mapped[int] = mapped_column(Integer)
    descuento_ausencias_centavos: Mapped[int] = mapped_column(Integer)
    aportes_centavos: Mapped[int] = mapped_column(Integer)
    neto_centavos: Mapped[int] = mapped_column(Integer)
