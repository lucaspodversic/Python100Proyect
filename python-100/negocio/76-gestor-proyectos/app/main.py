"""API del gestor de proyectos estilo Trello.

Todas las rutas de tablero exigen ser miembro; las de escritura exigen
permiso ``editor`` y la gestión de miembros, ``duenio``.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import date

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import servicio
from .auth import crear_auth
from .db import Base, crear_fabrica_sesiones, crear_motor
from .modelos import Actividad, Lista, Miembro, Permiso, Rol, Tablero, Tarjeta, Token, Usuario
from .servicio import ErrorNegocio, exigir


class TableroIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    listas: list[str] = Field(default_factory=lambda: ["Por hacer", "En curso", "Hecho"], max_length=20)


class MiembroIn(BaseModel):
    email: str
    permiso: Permiso


class ListaIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)


class TarjetaIn(BaseModel):
    titulo: str = Field(min_length=1, max_length=200)
    descripcion: str = Field(default="", max_length=10_000)
    vence: date | None = None
    etiquetas: list[str] = Field(default_factory=list, max_length=10)


class MoverIn(BaseModel):
    lista_id: int
    posicion: int = Field(ge=0)


class PosicionIn(BaseModel):
    posicion: int = Field(ge=0)


class AsignarIn(BaseModel):
    usuario_id: int | None


def _tarjeta(t: Tarjeta) -> dict:
    return {"id": t.id, "lista_id": t.lista_id, "titulo": t.titulo, "descripcion": t.descripcion,
            "posicion": t.posicion, "vence": t.vence.isoformat() if t.vence else None,
            "asignado_id": t.asignado_id, "etiquetas": [e for e in t.etiquetas.split(",") if e]}


def _tablero(t: Tablero) -> dict:
    """Vista completa: listas ordenadas con sus tarjetas ordenadas."""
    return {"id": t.id, "nombre": t.nombre,
            "listas": [{"id": l.id, "nombre": l.nombre, "posicion": l.posicion,
                        "tarjetas": [_tarjeta(x) for x in l.tarjetas]} for l in t.listas]}


def crear_app(url_bd: str = "sqlite:///proyectos.db", hoy: Callable[[], date] = date.today) -> FastAPI:
    """Fábrica de la aplicación (``hoy`` inyectable para tests de vencimiento)."""
    app = FastAPI(title="Gestor de proyectos", version="1.0.0")
    motor = crear_motor(url_bd)
    Base.metadata.create_all(motor)
    app.state.fabrica = crear_fabrica_sesiones(motor)
    auth = crear_auth(app.state.fabrica, Usuario, Token, Rol.USUARIO)
    app.include_router(auth.router)
    S = Depends(auth.obtener_sesion)
    yo = Depends(auth.usuario_actual)

    @app.exception_handler(ErrorNegocio)
    async def _err(_r: Request, e: ErrorNegocio) -> JSONResponse:
        return JSONResponse(status_code=e.codigo, content={"detail": e.mensaje})

    def lista_de(s: Session, lista_id: int, u: Usuario, minimo: Permiso) -> Lista:
        """Carga una lista verificando el permiso sobre su tablero."""
        lista = s.get(Lista, lista_id)
        if lista is None:
            raise ErrorNegocio("lista inexistente", 404)
        exigir(s, lista.tablero_id, u, minimo)
        return lista

    def tarjeta_de(s: Session, tid: int, u: Usuario, minimo: Permiso) -> Tarjeta:
        t = s.get(Tarjeta, tid)
        if t is None:
            raise ErrorNegocio("tarjeta inexistente", 404)
        exigir(s, t.lista.tablero_id, u, minimo)
        return t

    @app.post("/tableros", status_code=201)
    def crear_tablero(d: TableroIn, u: Usuario = yo, s: Session = S) -> dict:
        return _tablero(servicio.crear_tablero(s, u, d.nombre, d.listas))

    @app.get("/tableros")
    def mis_tableros(u: Usuario = yo, s: Session = S) -> list[dict]:
        filas = s.execute(select(Tablero, Miembro.permiso).join(Miembro).where(Miembro.usuario_id == u.id)
                          .order_by(Tablero.id))
        return [{"id": t.id, "nombre": t.nombre, "permiso": p.value} for t, p in filas]

    @app.get("/tableros/{tid}")
    def ver_tablero(tid: int, u: Usuario = yo, s: Session = S) -> dict:
        return _tablero(exigir(s, tid, u, Permiso.LECTOR))

    @app.delete("/tableros/{tid}", status_code=204)
    def borrar_tablero(tid: int, u: Usuario = yo, s: Session = S) -> None:
        s.delete(exigir(s, tid, u, Permiso.DUENIO))

    @app.post("/tableros/{tid}/miembros", status_code=201)
    def agregar_miembro(tid: int, d: MiembroIn, u: Usuario = yo, s: Session = S) -> dict:
        m = servicio.agregar_miembro(s, exigir(s, tid, u, Permiso.DUENIO), u, d.email, d.permiso)
        return {"usuario_id": m.usuario_id, "permiso": m.permiso.value}

    @app.post("/tableros/{tid}/listas", status_code=201)
    def crear_lista(tid: int, d: ListaIn, u: Usuario = yo, s: Session = S) -> dict:
        t = exigir(s, tid, u, Permiso.EDITOR)
        t.listas.append(Lista(nombre=d.nombre, posicion=len(t.listas)))
        s.flush()
        return {"id": t.listas[-1].id, "posicion": t.listas[-1].posicion}

    @app.post("/listas/{lid}/mover")
    def mover_lista(lid: int, d: PosicionIn, u: Usuario = yo, s: Session = S) -> dict:
        lista = lista_de(s, lid, u, Permiso.EDITOR)
        t = s.get(Tablero, lista.tablero_id)
        servicio.mover_lista(s, t, lista, d.posicion)
        return _tablero(t)

    @app.post("/listas/{lid}/tarjetas", status_code=201)
    def crear_tarjeta(lid: int, d: TarjetaIn, u: Usuario = yo, s: Session = S) -> dict:
        lista = lista_de(s, lid, u, Permiso.EDITOR)
        return _tarjeta(servicio.crear_tarjeta(s, lista, u, d.titulo, d.descripcion, d.vence, d.etiquetas))

    @app.post("/tarjetas/{tid}/mover")
    def mover_tarjeta(tid: int, d: MoverIn, u: Usuario = yo, s: Session = S) -> dict:
        t = tarjeta_de(s, tid, u, Permiso.EDITOR)
        destino = lista_de(s, d.lista_id, u, Permiso.EDITOR)
        return _tarjeta(servicio.mover_tarjeta(s, t, destino, d.posicion, u))

    @app.post("/tarjetas/{tid}/asignar")
    def asignar(tid: int, d: AsignarIn, u: Usuario = yo, s: Session = S) -> dict:
        return _tarjeta(servicio.asignar(s, tarjeta_de(s, tid, u, Permiso.EDITOR), d.usuario_id, u))

    @app.delete("/tarjetas/{tid}", status_code=204)
    def borrar_tarjeta(tid: int, u: Usuario = yo, s: Session = S) -> None:
        t = tarjeta_de(s, tid, u, Permiso.EDITOR)
        lista = t.lista
        lista.tarjetas.remove(t)  # delete-orphan la elimina
        servicio._renumerar(lista.tarjetas)

    @app.get("/tableros/{tid}/buscar")
    def buscar(tid: int, etiqueta: str | None = None, asignado_id: int | None = None,
               vencidas: bool = False, u: Usuario = yo, s: Session = S) -> list[dict]:
        """Filtros combinables por etiqueta, persona asignada y vencimiento."""
        t = exigir(s, tid, u, Permiso.LECTOR)
        res = [x for l in t.listas for x in l.tarjetas]
        if etiqueta:
            res = [x for x in res if etiqueta in x.etiquetas.split(",")]
        if asignado_id is not None:
            res = [x for x in res if x.asignado_id == asignado_id]
        if vencidas:
            ids = {x.id for x in servicio.vencidas(s, t, hoy())}
            res = [x for x in res if x.id in ids]
        return [_tarjeta(x) for x in res]

    @app.get("/tableros/{tid}/actividad")
    def actividad(tid: int, u: Usuario = yo, s: Session = S) -> list[str]:
        exigir(s, tid, u, Permiso.LECTOR)
        return list(s.scalars(select(Actividad.texto).where(Actividad.tablero_id == tid).order_by(Actividad.id)))

    return app


def __getattr__(nombre: str):  # pragma: no cover
    if nombre == "app":
        return crear_app()
    raise AttributeError(nombre)
