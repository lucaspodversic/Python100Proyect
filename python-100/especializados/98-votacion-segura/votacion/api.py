"""API HTTP (FastAPI).

Endpoints (prefijo ``/eleccion``):

========================  ========  ==============================================
Ruta                      Auth      Función
========================  ========  ==============================================
GET  /                    —         estado, opciones, clave pública y huella
POST /padron              admin     registrar votante → devuelve su token
POST /abrir, /cerrar      admin     cambiar estado
POST /firmar              token     ``{token, cegado}`` → ``{firma_cegada}``
POST /votar               anónimo   ``{serie, opcion, firma}`` → recibo
GET  /resultados          —         conteo (solo con la elección cerrada)
GET  /auditoria           —         cadena completa + verificación
========================  ========  ==============================================

Los enteros grandes viajan como **strings hexadecimales** (JSON no tiene
enteros de precisión arbitraria fiable en todos los clientes).

Nota de despliegue: ``/votar`` debe exponerse por un canal que oculte la IP
(Tor, mixnet, proxy de terceros) y SIN cookies/logs de acceso; si no, la IP
o la hora pueden re-vincular voto y votante.
"""
from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .servicio import Eleccion, ErrorVotacion, tokens_iguales

HEX = r"^[0-9a-f]+$"


class AltaVotante(BaseModel):
    votante: str = Field(min_length=1, max_length=100)


class PedidoFirma(BaseModel):
    token: str = Field(min_length=10, max_length=100)
    cegado: str = Field(pattern=HEX, max_length=2048)  # hex; 2048 chars alcanza para RSA-8192


class Voto(BaseModel):
    serie: str = Field(pattern=HEX, min_length=64, max_length=64)
    opcion: str = Field(min_length=1, max_length=200)
    firma: str = Field(pattern=HEX, max_length=2048)


def create_app(admin_token: str, eleccion: Eleccion | None = None, ruta_db: str = ":memory:",
               opciones: list[str] | None = None, id_eleccion: str = "eleccion-2026") -> FastAPI:
    if len(admin_token) < 16:
        raise ValueError("el token de administración debe tener al menos 16 caracteres")
    el = eleccion or Eleccion(id_eleccion, opciones or ["A", "B", "En blanco"], ruta_db=ruta_db)
    app = FastAPI(title="Votación segura", version="1.0.0")
    app.state.eleccion = el

    # Traducimos los errores de negocio a JSON con su status, en un solo lugar.
    @app.exception_handler(ErrorVotacion)
    async def _error(_req, exc: ErrorVotacion):  # type: ignore[no-untyped-def]
        return JSONResponse(status_code=exc.codigo, content={"detail": str(exc)})

    def admin(x_admin_token: str = Header(default="")) -> None:
        if not tokens_iguales(x_admin_token, admin_token):
            raise HTTPException(401, "credencial de administración inválida")

    @app.get("/eleccion")
    def info() -> dict:
        p = el.publica
        return {"id": el.id, "estado": el.estado.value, "opciones": el.opciones,
                "clave_publica": {"n": format(p.n, "x"), "e": p.e, "huella": p.huella()}}

    @app.post("/eleccion/padron", status_code=201, dependencies=[Depends(admin)])
    def alta(datos: AltaVotante) -> dict:
        return {"votante": datos.votante, "token": el.registrar(datos.votante)}

    @app.post("/eleccion/abrir", dependencies=[Depends(admin)])
    def abrir() -> dict:
        el.abrir()
        return {"estado": el.estado.value}

    @app.post("/eleccion/cerrar", dependencies=[Depends(admin)])
    def cerrar() -> dict:
        el.cerrar()
        return {"estado": el.estado.value, "cabeza": el.urna.cabeza()}

    @app.post("/eleccion/firmar")
    def firmar(p: PedidoFirma) -> dict:
        return {"firma_cegada": format(el.firmar(p.token, int(p.cegado, 16)), "x")}

    @app.post("/eleccion/votar", status_code=201)
    def votar(v: Voto) -> dict:
        return el.votar(v.serie, v.opcion, int(v.firma, 16))

    @app.get("/eleccion/resultados")
    def resultados() -> dict:
        return {"resultados": el.resultados(), "cabeza": el.urna.cabeza()}

    @app.get("/eleccion/auditoria")
    def auditoria() -> dict:
        return el.auditar()

    return app
