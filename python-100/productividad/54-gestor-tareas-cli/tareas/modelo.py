"""Modelo de dominio: Tarea, Prioridad y parseo de fechas amigable."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import IntEnum


class Prioridad(IntEnum):
    """Mayor número = más urgente (permite ordenar directamente)."""

    BAJA = 1
    MEDIA = 2
    ALTA = 3

    @classmethod
    def desde_texto(cls, t: str) -> "Prioridad":
        # Atajos de una letra: -p a / -p m / -p b.
        alias = {"b": "BAJA", "m": "MEDIA", "a": "ALTA"}
        t = t.strip().upper()
        t = alias.get(t.lower(), t)
        try:
            # Acceso por nombre del miembro (BAJA, MEDIA, ALTA).
            return cls[t]
        except KeyError:
            # Se convierte a ValueError (from None oculta el KeyError interno).
            raise ValueError(f"Prioridad inválida: {t!r} (baja/media/alta)") from None


# Con y sin tilde, para que funcione aunque el teclado no tenga acentos.
DIAS = {"lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2, "jueves": 3, "viernes": 4,
        "sabado": 5, "sábado": 5, "domingo": 6}


def parsear_fecha(texto: str, hoy: date) -> date:
    """Acepta 'AAAA-MM-DD', 'hoy', 'mañana', '+3' (días) o un día de la semana."""
    # Se normaliza el texto antes de compararlo.
    t = texto.strip().lower()
    if t == "hoy":
        return hoy
    if t in {"mañana", "manana"}:
        return hoy + timedelta(days=1)
    # "+N" = dentro de N días.
    if m := re.fullmatch(r"\+(\d+)", t):
        return hoy + timedelta(days=int(m.group(1)))
    if t in DIAS:  # próximo día con ese nombre (nunca hoy)
        # Si hoy es ese mismo día, "or 7" lleva a la semana siguiente.
        delta = (DIAS[t] - hoy.weekday()) % 7 or 7
        return hoy + timedelta(days=delta)
    try:
        # Último recurso: fecha ISO AAAA-MM-DD.
        return date.fromisoformat(t)
    except ValueError:
        raise ValueError(f"Fecha no reconocida: {texto!r}") from None


@dataclass
class Tarea:
    """Una tarea; `id` es None hasta que se guarda en la base."""
    titulo: str
    prioridad: Prioridad = Prioridad.MEDIA
    vence: date | None = None
    etiquetas: set[str] = field(default_factory=set)
    hecha: bool = False
    id: int | None = None

    def estado(self, hoy: date) -> str:
        """Texto corto para mostrar: hecha / vencida / hoy / pendiente."""
        if self.hecha:
            return "hecha"
        # Sólo pueden vencer las que tienen fecha.
        if self.vence and self.vence < hoy:
            return "VENCIDA"
        if self.vence == hoy:
            return "hoy"
        return "pendiente"

    def clave_orden(self) -> tuple:
        """Pendientes primero; luego fecha más cercana; luego prioridad alta."""
        # False < True deja las pendientes primero; sin fecha (date.max) van al final; -prioridad pone ALTA antes; el id desempata.
        return (self.hecha, self.vence or date.max, -self.prioridad, self.id or 0)
