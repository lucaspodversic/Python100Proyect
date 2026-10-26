"""Modelos: correo, condiciones y acciones de las reglas.

Las condiciones dentro de una regla se combinan con AND. Para expresar OR
se crean varias reglas.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from email.utils import parseaddr


@dataclass
class Correo:
    id: str
    remitente: str
    asunto: str
    fecha: dt.datetime
    etiquetas: list[str] = field(default_factory=list)
    tamano: int = 0  # bytes
    tiene_adjuntos: bool = False

    @property
    def email_remitente(self) -> str:
        """Sólo la dirección (``"Tienda <ofertas@tienda.com>"`` -> ``ofertas@tienda.com``)."""
        # parseaddr maneja comillas y nombres con "<>" mejor que un regex casero.
        return parseaddr(self.remitente)[1].lower()

    @property
    def dominio(self) -> str:
        # rpartition: toma lo que está después de la ÚLTIMA "@" (sin "@" devuelve la cadena entera).
        return self.email_remitente.rpartition("@")[2]


@dataclass
class Condicion:
    """Condiciones opcionales; las que quedan en ``None`` no se evalúan."""

    remitente_contiene: str | None = None
    dominio: str | None = None  # coincide también con subdominios
    asunto_regex: str | None = None
    mas_antiguo_que_dias: int | None = None
    con_etiqueta: str | None = None
    tamano_mayor_kb: int | None = None
    tiene_adjuntos: bool | None = None

    # Cada condición presente que falla corta con False (AND); las ausentes (None) se ignoran.
    # Si ninguna falla, la regla aplica. Una regla sin condiciones aplica a todo.
    def cumple(self, c: Correo, ahora: dt.datetime) -> bool:
        if self.remitente_contiene and self.remitente_contiene.lower() not in c.remitente.lower():
            return False
        if self.dominio:
            d = self.dominio.lower()
            # "github.com" coincide con "github.com" y "alerts.github.com", pero NO con "notgithub.com"
            # (por eso se exige el punto antes del sufijo).
            if not (c.dominio == d or c.dominio.endswith("." + d)):
                return False
        # re.search (no match): el patrón puede aparecer en cualquier parte del asunto.
        if self.asunto_regex and not re.search(self.asunto_regex, c.asunto, re.IGNORECASE):
            return False
        # "is not None" para que 0 sea un valor válido (y no se confunda con "sin condición").
        if self.mas_antiguo_que_dias is not None and (ahora - c.fecha).days < self.mas_antiguo_que_dias:
            return False
        if self.con_etiqueta and self.con_etiqueta not in c.etiquetas:
            return False
        # KB → bytes con 1024; "mayor" es estricto.
        if self.tamano_mayor_kb is not None and c.tamano <= self.tamano_mayor_kb * 1024:
            return False
        # Tri-estado: True exige adjuntos, False exige que no haya, None no importa.
        if self.tiene_adjuntos is not None and c.tiene_adjuntos != self.tiene_adjuntos:
            return False
        return True


@dataclass
class Accion:
    """Qué hacer con los correos que cumplen la regla."""

    archivar: bool = False  # quitar INBOX
    papelera: bool = False  # mover a la papelera (recuperable 30 días); nunca borrado definitivo
    etiquetar: list[str] = field(default_factory=list)
    marcar_leido: bool = False
    destacar: bool = False


@dataclass
class Regla:
    nombre: str
    condicion: Condicion
    accion: Accion
    detener: bool = True  # si cumple, no evaluar reglas siguientes
