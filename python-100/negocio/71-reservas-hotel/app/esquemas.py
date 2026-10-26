"""Esquemas Pydantic: validan la entrada y dan forma a la salida de la API."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RegistroIn(BaseModel):
    """Datos para registrar un cliente nuevo."""

    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=200)
    nombre: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    """Credenciales de inicio de sesión."""

    email: str
    password: str


class TokenOut(BaseModel):
    """Respuesta del login: el token se envía en la cabecera ``Authorization``."""

    token: str
    tipo: str = "Bearer"


class HabitacionIn(BaseModel):
    """Alta de habitación (solo administradores)."""

    numero: str = Field(min_length=1, max_length=10)
    tipo: str = Field(min_length=1, max_length=30)
    capacidad: int = Field(ge=1, le=10)
    precio_noche_centavos: int = Field(gt=0)


class HabitacionOut(HabitacionIn):
    """Habitación tal como la devuelve la API."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    activa: bool


class ReservaIn(BaseModel):
    """Solicitud de reserva. Valida que la salida sea posterior a la entrada."""

    habitacion_id: int
    entrada: date
    salida: date
    huespedes: int = Field(ge=1, le=10)

    @model_validator(mode="after")
    def _fechas_coherentes(self) -> "ReservaIn":
        # Validación de coherencia entre campos: no puede hacerse con Field.
        if self.salida <= self.entrada:
            raise ValueError("la fecha de salida debe ser posterior a la de entrada")
        return self


class ReservaOut(BaseModel):
    """Reserva devuelta por la API."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    habitacion_id: int
    usuario_id: int
    entrada: date
    salida: date
    huespedes: int
    total_centavos: int
    estado: str
