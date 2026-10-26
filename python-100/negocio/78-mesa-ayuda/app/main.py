"""API de la mesa de ayuda."""
from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import servicio
from .auth import crear_auth, crear_usuario
from .db import Base, crear_fabrica_sesiones, crear_motor
from .modelos import Estado, Prioridad, Rol, Ticket, Token, Usuario
from .servicio import ErrorNegocio


class TicketIn(BaseModel):
    """Alta de ticket por un cliente. Prioridad 'media' si no se indica; puede cambiarla
    después el staff.
    """
    asunto: str = Field(min_length=3, max_length=200)
    descripcion: str = Field(min_length=1, max_length=20_000)
    prioridad: Prioridad = Prioridad.MEDIA


class EstadoIn(BaseModel):
    """Pedido de transición de estado (las permitidas están en servicio.TRANSICIONES)."""
    estado: Estado


class ComentarioIn(BaseModel):
    """Comentario. ``interno=True`` = nota privada entre agentes (el cliente no puede crearlas
    ni verlas).
    """
    texto: str = Field(min_length=1, max_length=20_000)
    interno: bool = False


class PrioridadIn(BaseModel):
    """Nueva prioridad; recalcula los vencimientos de SLA."""
    prioridad: Prioridad


class RolIn(BaseModel):
    """Cambio de rol (solo admin)."""
    rol: Rol


def ahora_utc() -> datetime:
    """Hora actual en UTC sin zona (naive), que es como SQLite guarda las fechas. Se inyecta
    como ``reloj`` para que los tests controlen el tiempo.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def crear_app(url_bd: str = "sqlite:///tickets.db", admin_email: str = "admin@soporte.local",
              admin_password: str | None = None, reloj: Callable[[], datetime] = ahora_utc) -> FastAPI:
    """Arma la API: crea las tablas, siembra el admin si hay contraseña (por parámetro o
    SOPORTE_ADMIN_PASSWORD; nunca hay una contraseña por defecto), monta la
    autenticación y define las rutas. ``reloj`` permite simular el paso del tiempo para
    los SLA.
    """
    app = FastAPI(title="Mesa de ayuda", version="1.0.0")
    motor = crear_motor(url_bd)
    Base.metadata.create_all(motor)
    fabrica = app.state.fabrica = crear_fabrica_sesiones(motor)
    password = admin_password or os.environ.get("SOPORTE_ADMIN_PASSWORD")
    if password:
        with fabrica.begin() as s:
            if s.scalar(select(Usuario).where(Usuario.email == admin_email)) is None:
                crear_usuario(s, Usuario, admin_email, "Admin", password, Rol.ADMIN)
    auth = crear_auth(fabrica, Usuario, Token, Rol.CLIENTE)
    app.include_router(auth.router)
    S = Depends(auth.obtener_sesion)
    yo = Depends(auth.usuario_actual)
    staff = Depends(auth.requiere_rol(Rol.AGENTE, Rol.ADMIN))
    admin = Depends(auth.requiere_rol(Rol.ADMIN))
    agente = Depends(auth.requiere_rol(Rol.AGENTE))

    @app.exception_handler(ErrorNegocio)
    async def _err(_r: Request, e: ErrorNegocio) -> JSONResponse:
        """Traduce ErrorNegocio a una respuesta JSON con su código y {'detail': mensaje}, el
        mismo formato que usan las HTTPException de FastAPI.
        """
        return JSONResponse(status_code=e.codigo, content={"detail": e.mensaje})

    def vista(t: Ticket, u: Usuario) -> dict:
        """Serializa el ticket; las notas internas se ocultan a los clientes."""
        return {"id": t.id, "asunto": t.asunto, "descripcion": t.descripcion, "prioridad": t.prioridad.value,
                "estado": t.estado.value, "cliente_id": t.cliente_id, "agente_id": t.agente_id,
                "vence_respuesta": t.vence_respuesta.isoformat(), "vence_resolucion": t.vence_resolucion.isoformat(),
                "sla": servicio.estado_sla(t, reloj()),
                "comentarios": [{"autor_id": c.autor_id, "texto": c.texto, "interno": c.interno}
                                for c in t.comentarios if u.rol != Rol.CLIENTE or not c.interno]}

    @app.patch("/usuarios/{uid}/rol", dependencies=[admin])
    def cambiar_rol(uid: int, d: RolIn, s: Session = S) -> dict:
        """Admin: cambia el rol de un usuario (así se crean agentes)."""
        u = s.get(Usuario, uid)
        if u is None:
            raise HTTPException(404, "usuario inexistente")
        u.rol = d.rol
        return {"id": u.id, "rol": u.rol.value}

    @app.post("/tickets", status_code=201)
    def crear(d: TicketIn, u: Usuario = yo, s: Session = S) -> dict:
        """Cliente: abre un ticket que se asigna solo al agente con menos tickets activos."""
        if u.rol != Rol.CLIENTE:
            raise HTTPException(403, "solo los clientes abren tickets")
        return vista(servicio.crear_ticket(s, u, d.asunto, d.descripcion, d.prioridad, reloj()), u)

    @app.get("/tickets")
    def listar(estado: Estado | None = None, mios: bool = False, u: Usuario = yo, s: Session = S) -> list[dict]:
        """Clientes ven los suyos; el staff ve todos (``mios=true`` → asignados a mí)."""
        q = select(Ticket).order_by(Ticket.vence_resolucion)  # lo más urgente primero
        if u.rol == Rol.CLIENTE:
            q = q.where(Ticket.cliente_id == u.id)
        elif mios:
            q = q.where(Ticket.agente_id == u.id)
        if estado:
            q = q.where(Ticket.estado == estado)
        return [vista(t, u) for t in s.scalars(q)]

    @app.get("/tickets/incumplidos", dependencies=[staff])
    def incumplidos(s: Session = S) -> list[int]:
        """Tickets activos con algún SLA vencido (para el tablero de supervisión)."""
        ahora = reloj()
        activos = s.scalars(select(Ticket).where(Ticket.estado.not_in([Estado.RESUELTO, Estado.CERRADO])))
        return [t.id for t in activos if any(servicio.estado_sla(t, ahora).values())]

    @app.get("/tickets/{tid}")
    def ver(tid: int, u: Usuario = yo, s: Session = S) -> dict:
        """Ticket con sus comentarios visibles para quien lo pide (404 si no puede verlo, así
        no se revela que existe).
        """
        return vista(servicio.obtener(s, tid, u), u)

    @app.post("/tickets/{tid}/estado")
    def estado(tid: int, d: EstadoIn, u: Usuario = yo, s: Session = S) -> dict:
        """Aplica una transición validando estado actual, rol y que el agente sea el asignado."""
        t = servicio.obtener(s, tid, u)
        return vista(servicio.transicionar(s, t, u, d.estado, reloj()), u)

    @app.post("/tickets/{tid}/comentarios", status_code=201)
    def comentar(tid: int, d: ComentarioIn, u: Usuario = yo, s: Session = S) -> dict:
        """Agrega un comentario. La primera respuesta del staff marca el SLA de respuesta y la
        respuesta del cliente reactiva un ticket en 'esperando_cliente'.
        """
        t = servicio.obtener(s, tid, u)
        servicio.comentar(s, t, u, d.texto, d.interno, reloj())
        return vista(t, u)

    @app.post("/tickets/{tid}/tomar")
    def tomar(tid: int, u: Usuario = agente, s: Session = S) -> dict:
        """Agente: toma un ticket sin asignar. Es atómico: si varios lo intentan a la vez, gana
        uno solo.
        """
        servicio.obtener(s, tid, u)
        if not servicio.tomar(s, tid, u):
            raise HTTPException(409, "el ticket ya tiene agente")
        return {"id": tid, "agente_id": u.id}

    @app.post("/tickets/{tid}/prioridad", dependencies=[staff])
    def prioridad(tid: int, d: PrioridadIn, u: Usuario = yo, s: Session = S) -> dict:
        """Staff: cambia la prioridad y recalcula los vencimientos desde la creación del
        ticket.
        """
        return vista(servicio.cambiar_prioridad(servicio.obtener(s, tid, u), d.prioridad), u)

    return app


def __getattr__(nombre: str):  # pragma: no cover
    """Atributo perezoso del módulo: ``uvicorn app.main:app`` pide ``app`` y recién ahí se
    crea, así importar el módulo (por ejemplo en los tests) no abre ninguna base.
    """
    if nombre == "app":
        return crear_app()
    raise AttributeError(nombre)
