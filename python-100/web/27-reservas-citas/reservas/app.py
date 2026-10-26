"""API HTTP de reservas.

GET  /profesionales/{p}/disponibles?servicio=corte&dia=2026-11-02
POST /reservas                       {profesional, servicio, inicio, cliente, email}
POST /reservas/{id}/cancelar         {codigo}
GET  /profesionales/{p}/agenda?dia=  (requiere X-Admin-Token)
"""
from __future__ import annotations

import os
import secrets
from datetime import date, datetime

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from reservas.agenda import Agenda, ErrorAgenda

# Configuración de ejemplo de un negocio (se puede reemplazar al crear la app)
# Las claves de cada día son números de weekday() (0 = lunes).
HORARIOS_DEMO = {
    "ana": {d: ["09:00-13:00", "14:00-18:00"] for d in range(0, 5)},   # lunes a viernes
    "bruno": {d: ["10:00-14:00"] for d in (1, 3, 5)},                  # mar, jue, sáb
}
SERVICIOS_DEMO = {"corte": 30, "barba": 15, "color": 90}


# Pydantic parsea "2026-11-02T09:00:00" a datetime automáticamente.
class ReservaIn(BaseModel):
    profesional: str
    servicio: str
    inicio: datetime
    cliente: str
    email: str


class CancelacionIn(BaseModel):
    codigo: str


def crear_app(agenda: Agenda | None = None, token_admin: str | None = None) -> FastAPI:
    app = FastAPI(title="Reservas de citas")
    # Agenda inyectable: los tests pasan una con reloj y horarios controlados.
    ag = agenda or Agenda(HORARIOS_DEMO, SERVICIOS_DEMO, os.environ.get("RESERVAS_DB", ":memory:"))
    token_admin = token_admin or os.environ.get("RESERVAS_ADMIN_TOKEN")

    # Traduce los errores del motor a JSON con el código que el motor eligió.
    @app.exception_handler(ErrorAgenda)
    async def _err(_r: Request, e: ErrorAgenda):
        return JSONResponse(status_code=e.codigo, content={"detail": str(e)})

    @app.get("/servicios")
    def servicios():
        return ag.servicios

    @app.get("/profesionales/{p}/disponibles")
    def disponibles(p: str, servicio: str, dia: date):
        # Para el cliente alcanza con la hora: el día ya lo mandó él.
        return [h.strftime("%H:%M") for h in ag.disponibles(p, servicio, dia)]

    @app.post("/reservas", status_code=201)
    def reservar(r: ReservaIn):
        # Se trabaja con horas locales "naive" del negocio
        return ag.reservar(r.profesional, r.servicio, r.inicio.replace(tzinfo=None), r.cliente, r.email)

    @app.post("/reservas/{rid}/cancelar")
    def cancelar(rid: int, c: CancelacionIn):
        ag.cancelar(rid, c.codigo)
        return {"estado": "cancelada"}

    @app.get("/profesionales/{p}/agenda")
    def agenda_dia(p: str, dia: date, x_admin_token: str = Header(default="")):
        # La agenda del día tiene datos personales (nombres): solo con token.
        if not token_admin or not secrets.compare_digest(x_admin_token, token_admin):
            raise HTTPException(401, "Solo personal autorizado")
        return ag.del_dia(p, dia)

    return app


app = crear_app()
