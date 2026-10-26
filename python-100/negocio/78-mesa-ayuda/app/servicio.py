"""Reglas de la mesa de ayuda: máquina de estados, SLA y asignación."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .modelos import Cambio, Comentario, Estado, Prioridad, Rol, Ticket, Usuario

#: SLA por prioridad: (primera respuesta, resolución).
SLA: dict[Prioridad, tuple[timedelta, timedelta]] = {
    Prioridad.URGENTE: (timedelta(hours=1), timedelta(hours=4)),
    Prioridad.ALTA: (timedelta(hours=4), timedelta(hours=24)),
    Prioridad.MEDIA: (timedelta(hours=8), timedelta(days=3)),
    Prioridad.BAJA: (timedelta(hours=24), timedelta(days=7)),
}

#: Transiciones permitidas y qué roles pueden hacerlas.
#: Clave: (estado actual, estado nuevo) → roles autorizados.
TRANSICIONES: dict[tuple[Estado, Estado], set[Rol]] = {
    (Estado.ABIERTO, Estado.EN_PROGRESO): {Rol.AGENTE, Rol.ADMIN},
    (Estado.EN_PROGRESO, Estado.ESPERANDO_CLIENTE): {Rol.AGENTE, Rol.ADMIN},
    (Estado.ESPERANDO_CLIENTE, Estado.EN_PROGRESO): {Rol.AGENTE, Rol.ADMIN, Rol.CLIENTE},
    (Estado.EN_PROGRESO, Estado.RESUELTO): {Rol.AGENTE, Rol.ADMIN},
    (Estado.RESUELTO, Estado.ABIERTO): {Rol.CLIENTE, Rol.ADMIN},  # reapertura
    (Estado.RESUELTO, Estado.CERRADO): {Rol.CLIENTE, Rol.AGENTE, Rol.ADMIN},
    (Estado.ABIERTO, Estado.CERRADO): {Rol.CLIENTE, Rol.ADMIN},  # el cliente desiste
}

DIAS_REAPERTURA = 7


class ErrorNegocio(Exception):
    """Violación de una regla de negocio (``codigo`` = estado HTTP)."""
    def __init__(self, mensaje: str, codigo: int = 400) -> None:
        """``mensaje`` va al cliente como 'detail' y ``codigo`` es el estado HTTP (400 por
        defecto; 404, 409, etc. según el caso).
        """
        super().__init__(mensaje)
        self.mensaje, self.codigo = mensaje, codigo


def plazos(prioridad: Prioridad, desde: datetime) -> tuple[datetime, datetime]:
    """Calcula los vencimientos SLA (horas corridas, sin calendario laboral)."""
    resp, resol = SLA[prioridad]
    return desde + resp, desde + resol


def estado_sla(t: Ticket, ahora: datetime) -> dict[str, bool]:
    """Indica si el ticket incumplió (o está incumpliendo) cada SLA."""
    resp = t.primera_respuesta or ahora
    fin = t.resuelto_en or ahora
    return {"respuesta_incumplida": resp > t.vence_respuesta,
            "resolucion_incumplida": fin > t.vence_resolucion}


def agente_con_menos_carga(s: Session) -> Usuario | None:
    """Balanceo: el agente con menos tickets activos (empate → menor id)."""
    activos = (select(Ticket.agente_id, func.count().label("n"))
               .where(Ticket.estado.in_([Estado.ABIERTO, Estado.EN_PROGRESO, Estado.ESPERANDO_CLIENTE]))
               .group_by(Ticket.agente_id).subquery())
    q = (select(Usuario).outerjoin(activos, activos.c.agente_id == Usuario.id)
         .where(Usuario.rol == Rol.AGENTE)
         .order_by(func.coalesce(activos.c.n, 0), Usuario.id).limit(1))
    return s.scalar(q)


def crear_ticket(s: Session, cliente: Usuario, asunto: str, descripcion: str, prioridad: Prioridad,
                 ahora: datetime, autoasignar: bool = True) -> Ticket:
    """Crea un ticket con sus plazos SLA y (opcionalmente) lo asigna por carga."""
    vr, vf = plazos(prioridad, ahora)
    agente = agente_con_menos_carga(s) if autoasignar else None
    t = Ticket(asunto=asunto, descripcion=descripcion, prioridad=prioridad, cliente_id=cliente.id,
               agente_id=agente.id if agente else None, creado=ahora, vence_respuesta=vr, vence_resolucion=vf)
    s.add(t)
    s.flush()
    return t


def puede_ver(t: Ticket, u: Usuario) -> bool:
    """Clientes: solo sus tickets. Agentes y admin: todos."""
    return u.rol != Rol.CLIENTE or t.cliente_id == u.id


def obtener(s: Session, tid: int, u: Usuario) -> Ticket:
    """Busca un ticket que el usuario pueda ver. 'No existe' y 'no es tuyo' dan el mismo 404 a
    propósito, para no filtrar información.
    """
    t = s.get(Ticket, tid)
    if t is None or not puede_ver(t, u):
        raise ErrorNegocio("ticket inexistente", 404)
    return t


def transicionar(s: Session, t: Ticket, u: Usuario, nuevo: Estado, ahora: datetime) -> Ticket:
    """Aplica una transición validando la máquina de estados y el rol."""
    roles = TRANSICIONES.get((t.estado, nuevo))
    if roles is None:
        raise ErrorNegocio(f"transición inválida: {t.estado.value} → {nuevo.value}", 409)
    if u.rol not in roles:
        raise ErrorNegocio("tu rol no puede hacer esta transición", 403)
    if u.rol == Rol.AGENTE and t.agente_id not in (None, u.id):
        raise ErrorNegocio("el ticket está asignado a otro agente", 403)
    if t.estado == Estado.RESUELTO and nuevo == Estado.ABIERTO:
        if ahora - (t.resuelto_en or ahora) > timedelta(days=DIAS_REAPERTURA):
            raise ErrorNegocio(f"solo se puede reabrir dentro de {DIAS_REAPERTURA} días", 409)
        t.resuelto_en = None
    if nuevo == Estado.RESUELTO:
        t.resuelto_en = ahora
    if nuevo == Estado.EN_PROGRESO and t.agente_id is None and u.rol == Rol.AGENTE:
        t.agente_id = u.id  # quien lo empieza, lo toma
    s.add(Cambio(ticket_id=t.id, autor_id=u.id, de=t.estado.value, a=nuevo.value, fecha=ahora))
    t.estado = nuevo
    return t


def comentar(s: Session, t: Ticket, u: Usuario, texto: str, interno: bool, ahora: datetime) -> Comentario:
    """Agrega un comentario. La primera respuesta pública de un agente cumple el SLA de respuesta."""
    if t.estado == Estado.CERRADO:
        raise ErrorNegocio("el ticket está cerrado", 409)
    if interno and u.rol == Rol.CLIENTE:
        raise ErrorNegocio("los clientes no pueden crear notas internas", 403)
    if u.rol in (Rol.AGENTE, Rol.ADMIN) and not interno and t.primera_respuesta is None:
        t.primera_respuesta = ahora
    c = Comentario(ticket_id=t.id, autor_id=u.id, texto=texto, interno=interno, fecha=ahora)
    t.comentarios.append(c)
    # Si el cliente responde mientras se esperaba su respuesta, vuelve a "en progreso".
    if u.rol == Rol.CLIENTE and t.estado == Estado.ESPERANDO_CLIENTE:
        transicionar(s, t, u, Estado.EN_PROGRESO, ahora)
    s.flush()
    return c


def tomar(s: Session, tid: int, agente: Usuario) -> bool:
    """Un agente toma un ticket sin asignar de forma **atómica**.

    ``UPDATE ... WHERE agente_id IS NULL``: si dos agentes lo intentan a la
    vez, solo uno modifica la fila (rowcount 1); el otro recibe 0.
    """
    r = s.execute(update(Ticket).where(Ticket.id == tid, Ticket.agente_id.is_(None))
                  .values(agente_id=agente.id).execution_options(synchronize_session=False))
    return r.rowcount == 1


def cambiar_prioridad(t: Ticket, prioridad: Prioridad) -> Ticket:
    """Cambia la prioridad y recalcula los plazos desde la creación."""
    t.prioridad = prioridad
    t.vence_respuesta, t.vence_resolucion = plazos(prioridad, t.creado)
    return t
