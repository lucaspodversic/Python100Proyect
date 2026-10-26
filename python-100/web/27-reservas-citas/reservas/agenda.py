"""Motor de agenda: horarios de atención, cálculo de huecos y reservas.

Reglas:
- Cada profesional tiene un horario semanal (por día: lista de franjas HH:MM-HH:MM).
- Cada servicio tiene una duración en minutos.
- Los turnos se ofrecen en una grilla de `paso_min` minutos (por defecto 15).
- Dos reservas ACTIVAS del mismo profesional no pueden solaparse.
- No se puede reservar en el pasado ni con menos de `anticipacion_min` minutos.
"""
from __future__ import annotations

import secrets
import sqlite3
import threading
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Callable

# Las reservas no se borran al cancelar: cambian de estado ('activa' ->
# 'cancelada') para conservar el historial. El índice (profesional, inicio)
# acelera la búsqueda de turnos ocupados de un día.
ESQUEMA = """
CREATE TABLE IF NOT EXISTS reservas (
  id INTEGER PRIMARY KEY AUTOINCREMENT, profesional TEXT NOT NULL, servicio TEXT NOT NULL,
  cliente TEXT NOT NULL, email TEXT NOT NULL, inicio TEXT NOT NULL, fin TEXT NOT NULL,
  codigo TEXT NOT NULL, estado TEXT NOT NULL DEFAULT 'activa');
CREATE INDEX IF NOT EXISTS idx_res_prof ON reservas(profesional, inicio);
"""


# Error de negocio con código HTTP sugerido (404, 403, 409...).
class ErrorAgenda(Exception):
    def __init__(self, msg: str, codigo: int = 400) -> None:
        super().__init__(msg)
        self.codigo = codigo


@dataclass(frozen=True)
class Franja:
    """Intervalo horario dentro de un día."""
    desde: time
    hasta: time

    @classmethod
    def parse(cls, texto: str) -> "Franja":
        """Convierte '09:00-13:00' en una Franja."""
        # time.fromisoformat valida el formato HH:MM (lanza ValueError si no).
        a, b = texto.split("-")
        f = cls(time.fromisoformat(a), time.fromisoformat(b))
        # Una franja de largo cero o invertida es un error de configuración.
        if f.desde >= f.hasta:
            raise ValueError(f"Franja inválida: {texto}")
        return f


def solapan(a_ini: datetime, a_fin: datetime, b_ini: datetime, b_fin: datetime) -> bool:
    """Dos intervalos semiabiertos [ini, fin) se solapan si cada uno empieza antes de que termine el otro."""
    # Intervalos semiabiertos: un turno 9:00-9:30 y otro 9:30-10:00 NO se
    # solapan (el fin de uno es el inicio del otro). Es la convención que
    # permite turnos consecutivos sin huecos.
    return a_ini < b_fin and b_ini < a_fin


class Agenda:
    def __init__(self, horarios: dict[str, dict[int, list[str]]], servicios: dict[str, int],
                 ruta_db: str = ":memory:", paso_min: int = 15, anticipacion_min: int = 60,
                 reloj: Callable[[], datetime] = datetime.now) -> None:
        """
        horarios:  {"ana": {0: ["09:00-13:00", "14:00-18:00"], ...}}  (0 = lunes)
        servicios: {"corte": 30, "color": 90}  (duración en minutos)
        """
        # Se parsean las franjas una sola vez al crear la agenda: si hay un error
        # de configuración, falla al arrancar y no en medio de una reserva.
        self.horarios = {p: {d: [Franja.parse(f) for f in fs] for d, fs in dias.items()} for p, dias in horarios.items()}
        self.servicios = servicios
        self.paso = timedelta(minutes=paso_min)
        self.anticipacion = timedelta(minutes=anticipacion_min)
        # Reloj inyectable (por defecto datetime.now): los tests fijan "ahora".
        self.reloj = reloj
        self.con = sqlite3.connect(ruta_db, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(ESQUEMA)
        self.lock = threading.Lock()

    def _validar(self, profesional: str, servicio: str) -> timedelta:
        if profesional not in self.horarios:
            raise ErrorAgenda("Profesional inexistente", 404)
        if servicio not in self.servicios:
            raise ErrorAgenda("Servicio inexistente", 404)
        # Devuelve la duración para no tener que buscarla de nuevo.
        return timedelta(minutes=self.servicios[servicio])

    def _ocupados(self, profesional: str, dia: date) -> list[tuple[datetime, datetime]]:
        """Reservas activas del profesional en ese día."""
        filas = self.con.execute(
            # Las canceladas no ocupan lugar. substr(inicio, 1, 10) = fecha AAAA-MM-DD.
            "SELECT inicio, fin FROM reservas WHERE profesional = ? AND estado = 'activa' AND substr(inicio,1,10) = ?",
            (profesional, dia.isoformat())).fetchall()
        return [(datetime.fromisoformat(f[0]), datetime.fromisoformat(f[1])) for f in filas]

    def disponibles(self, profesional: str, servicio: str, dia: date) -> list[datetime]:
        """Calcula todos los inicios posibles para el servicio en ese día."""
        duracion = self._validar(profesional, servicio)
        ocupados = self._ocupados(profesional, dia)
        # Nada antes de "ahora + anticipación" (ej.: 1 h para que el negocio se organice).
        limite = self.reloj() + self.anticipacion
        huecos: list[datetime] = []
        # weekday(): 0 = lunes ... 6 = domingo. Un día sin franjas => sin turnos.
        for franja in self.horarios[profesional].get(dia.weekday(), []):
            t = datetime.combine(dia, franja.desde)
            fin_franja = datetime.combine(dia, franja.hasta)
            # El turno tiene que entrar completo dentro de la franja
            while t + duracion <= fin_franja:
                # Candidato válido: después del límite y sin chocar con ninguna reserva.
                # Con pocas reservas por día, comparar contra todas (O(n)) es suficiente.
                if t >= limite and not any(solapan(t, t + duracion, a, b) for a, b in ocupados):
                    huecos.append(t)
                # Grilla fija: los turnos empiezan en múltiplos de `paso` desde el inicio
                # de la franja (9:00, 9:15, 9:30...).
                t += self.paso
        return huecos

    def reservar(self, profesional: str, servicio: str, inicio: datetime, cliente: str, email: str) -> dict:
        """Crea una reserva si el horario sigue libre (verificación bajo candado)."""
        # Validación mínima del email (la real sería enviar un mail de confirmación).
        if "@" not in email or not cliente.strip():
            raise ErrorAgenda("Datos del cliente inválidos")
        with self.lock:
            # Recalcular dentro del candado evita que dos clientes tomen el mismo turno
            # Al exigir que el inicio esté en la lista de huecos también se rechazan
            # horarios fuera de grilla (9:07), fuera de franja o en el pasado.
            if inicio not in self.disponibles(profesional, servicio, inicio.date()):
                raise ErrorAgenda("Horario no disponible", 409)
            fin = inicio + timedelta(minutes=self.servicios[servicio])
            # Código secreto de cancelación: así no hace falta un sistema de cuentas.
            codigo = secrets.token_urlsafe(8)
            cur = self.con.execute(
                "INSERT INTO reservas (profesional, servicio, cliente, email, inicio, fin, codigo)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (profesional, servicio, cliente.strip(), email, inicio.isoformat(), fin.isoformat(), codigo))
            self.con.commit()
        return {"id": cur.lastrowid, "profesional": profesional, "servicio": servicio,
                "inicio": inicio.isoformat(), "fin": fin.isoformat(), "codigo_cancelacion": codigo}

    def cancelar(self, reserva_id: int, codigo: str) -> None:
        """Cancela con el código entregado al reservar; libera el horario."""
        with self.lock:
            f = self.con.execute("SELECT * FROM reservas WHERE id = ?", (reserva_id,)).fetchone()
            if f is None:
                raise ErrorAgenda("Reserva inexistente", 404)
            # Tiempo constante: no se puede adivinar el código carácter por carácter.
            if not secrets.compare_digest(f["codigo"], codigo):
                raise ErrorAgenda("Código incorrecto", 403)
            if f["estado"] != "activa":
                raise ErrorAgenda("La reserva ya estaba cancelada", 409)
            # Un turno que ya empezó o pasó no se puede cancelar.
            if datetime.fromisoformat(f["inicio"]) <= self.reloj():
                raise ErrorAgenda("No se puede cancelar un turno pasado", 409)
            self.con.execute("UPDATE reservas SET estado = 'cancelada' WHERE id = ?", (reserva_id,))
            self.con.commit()

    def del_dia(self, profesional: str, dia: date) -> list[dict]:
        """Agenda del día de un profesional (vista interna del negocio)."""
        return [dict(f) for f in self.con.execute(
            "SELECT id, servicio, cliente, inicio, fin FROM reservas WHERE profesional = ? AND estado='activa'"
            " AND substr(inicio,1,10) = ? ORDER BY inicio", (profesional, dia.isoformat()))]
