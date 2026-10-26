"""API de reserva de vuelos.

El reloj (``ahora``) es inyectable para poder testear la expiración de las
retenciones sin esperar 15 minutos reales.
"""
from __future__ import annotations

import os
from collections.abc import Callable
from datetime import date, datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import servicio
from .auth import crear_auth, crear_usuario
from .db import Base, crear_fabrica_sesiones, crear_motor
from .modelos import Reserva, Rol, Token, Usuario, Vuelo


def ahora_utc() -> datetime:
    """Hora actual en UTC sin zona (convención del proyecto)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class VueloIn(BaseModel):
    codigo: str = Field(pattern=r"^[A-Z0-9]{2}\d{1,4}$")
    origen: str = Field(pattern=r"^[A-Z]{3}$")
    destino: str = Field(pattern=r"^[A-Z]{3}$")
    salida: datetime
    filas: int = Field(ge=1, le=80)
    columnas: str = Field(pattern=r"^[A-Z]{1,10}$")
    precio_base_centavos: int = Field(gt=0)


class RetencionIn(BaseModel):
    vuelo_id: int
    asiento: str
    pasajero: str = Field(min_length=1, max_length=120)


def _reserva(r: Reserva) -> dict:
    return {"pnr": r.pnr, "vuelo_id": r.vuelo_id, "asiento": r.asiento, "pasajero": r.pasajero,
            "precio_centavos": r.precio_centavos, "estado": r.estado.value,
            "expira_en": r.expira_en.isoformat() if r.expira_en else None}


def crear_app(url_bd: str = "sqlite:///vuelos.db", admin_email: str = "admin@vuelos.local",
              admin_password: str | None = None, reloj: Callable[[], datetime] = ahora_utc) -> FastAPI:
    """Fábrica de la aplicación."""
    app = FastAPI(title="Reserva de vuelos", version="1.0.0")
    motor = crear_motor(url_bd)
    Base.metadata.create_all(motor)
    fabrica = crear_fabrica_sesiones(motor)
    app.state.fabrica, app.state.reloj = fabrica, reloj
    password = admin_password or os.environ.get("VUELOS_ADMIN_PASSWORD")
    if password:
        with fabrica.begin() as s:
            if s.scalar(select(Usuario).where(Usuario.email == admin_email)) is None:
                crear_usuario(s, Usuario, admin_email, "Admin", password, Rol.ADMIN)

    auth = crear_auth(fabrica, Usuario, Token, Rol.CLIENTE)
    app.include_router(auth.router)
    S = Depends(auth.obtener_sesion)
    yo = Depends(auth.usuario_actual)
    admin = Depends(auth.requiere_rol(Rol.ADMIN))

    @app.exception_handler(servicio.ErrorNegocio)
    async def _err(_r: Request, e: servicio.ErrorNegocio) -> JSONResponse:
        """Traduce ErrorNegocio a una respuesta JSON con su código y {'detail': mensaje}, el
        mismo formato que usan las HTTPException de FastAPI.
        """
        return JSONResponse(status_code=e.codigo, content={"detail": e.mensaje})

    def vuelo_o_404(s: Session, vid: int) -> Vuelo:
        v = s.get(Vuelo, vid)
        if v is None:
            raise HTTPException(404, "vuelo inexistente")
        return v

    @app.post("/vuelos", status_code=201, dependencies=[admin])
    def crear_vuelo(d: VueloIn, s: Session = S) -> dict:
        if d.origen == d.destino:
            raise HTTPException(400, "origen y destino deben ser distintos")
        datos = d.model_dump()
        # Guardamos en UTC naive según la convención del proyecto.
        if d.salida.tzinfo is not None:
            datos["salida"] = d.salida.astimezone(timezone.utc).replace(tzinfo=None)
        v = Vuelo(**datos)
        s.add(v)
        s.flush()
        return {"id": v.id, "codigo": v.codigo, "capacidad": v.capacidad}

    @app.get("/vuelos/buscar")
    def buscar(origen: str, destino: str, fecha: date, s: Session = S) -> list[dict]:
        """Búsqueda por ruta y día, con asientos libres y precio actual."""
        ahora = app.state.reloj()
        res = []
        for v in servicio.buscar(s, origen, destino, fecha, ahora):
            servicio.liberar_vencidas(s, ahora, v.id)
            libres = round(v.capacidad * (1 - servicio.ocupacion(s, v)))
            res.append({"id": v.id, "codigo": v.codigo, "salida": v.salida.isoformat(),
                        "asientos_libres": libres, "precio_centavos": servicio.precio_actual(s, v)})
        return res

    @app.get("/vuelos/{vid}/asientos")
    def asientos(vid: int, s: Session = S) -> dict[str, bool]:
        return servicio.mapa_asientos(s, vuelo_o_404(s, vid), app.state.reloj())

    @app.post("/reservas", status_code=201)
    def retener(d: RetencionIn, u: Usuario = yo, s: Session = S) -> dict:
        return _reserva(servicio.retener(s, u, d.vuelo_id, d.asiento, d.pasajero, app.state.reloj()))

    @app.post("/reservas/{pnr}/confirmar")
    def confirmar(pnr: str, u: Usuario = yo, s: Session = S) -> dict:
        return _reserva(servicio.confirmar(s, u, pnr, app.state.reloj()))

    @app.post("/reservas/{pnr}/cancelar")
    def cancelar(pnr: str, u: Usuario = yo, s: Session = S) -> dict:
        return _reserva(servicio.cancelar(s, u, pnr))

    @app.get("/reservas")
    def mis_reservas(u: Usuario = yo, s: Session = S) -> list[dict]:
        servicio.liberar_vencidas(s, app.state.reloj())
        return [_reserva(r) for r in s.scalars(select(Reserva).where(Reserva.usuario_id == u.id).order_by(Reserva.id))]

    return app


def __getattr__(nombre: str):  # pragma: no cover - instancia perezosa para uvicorn
    """Atributo perezoso del módulo: ``uvicorn app.main:app`` pide ``app`` y recién ahí se
    crea, así importar el módulo (por ejemplo en los tests) no abre ninguna base.
    """
    if nombre == "app":
        return crear_app()
    raise AttributeError(nombre)
