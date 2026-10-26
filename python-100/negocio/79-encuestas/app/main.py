"""API de encuestas.

- Creadores (autenticados): crean encuestas, generan códigos, ven resultados.
- Público (sin cuenta): ve la encuesta por su ``slug`` y responde.
"""
from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import graficos, servicio
from .auth import crear_auth
from .db import Base, crear_fabrica_sesiones, crear_motor
from .modelos import Encuesta, Pregunta, Rol, TipoPregunta, Token, Usuario
from .servicio import ErrorNegocio


class PreguntaIn(BaseModel):
    texto: str = Field(min_length=1, max_length=500)
    tipo: TipoPregunta
    opciones: list[str] = Field(default_factory=list, max_length=20)
    obligatoria: bool = True


class EncuestaIn(BaseModel):
    titulo: str = Field(min_length=3, max_length=200)
    preguntas: list[PreguntaIn] = Field(min_length=1, max_length=50)
    cierra_en: datetime | None = None


class RespuestaIn(BaseModel):
    valores: dict[str, Any]
    codigo: str | None = None


class CodigosIn(BaseModel):
    cantidad: int = Field(ge=1, le=1000)


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def crear_app(url_bd: str = "sqlite:///encuestas.db", reloj: Callable[[], datetime] = ahora_utc) -> FastAPI:
    app = FastAPI(title="Encuestas", version="1.0.0")
    motor = crear_motor(url_bd)
    Base.metadata.create_all(motor)
    app.state.fabrica = crear_fabrica_sesiones(motor)
    auth = crear_auth(app.state.fabrica, Usuario, Token, Rol.CREADOR)
    app.include_router(auth.router)
    S = Depends(auth.obtener_sesion)
    yo = Depends(auth.usuario_actual)

    @app.exception_handler(ErrorNegocio)
    async def _err(_r: Request, e: ErrorNegocio) -> JSONResponse:
        """Traduce ErrorNegocio a una respuesta JSON con su código y {'detail': mensaje}, el
        mismo formato que usan las HTTPException de FastAPI.
        """
        return JSONResponse(status_code=e.codigo, content={"detail": e.mensaje})

    def propia(s: Session, eid: int, u: Usuario) -> Encuesta:
        """La encuesta si pertenece al usuario (o es admin)."""
        e = s.get(Encuesta, eid)
        if e is None or (e.creador_id != u.id and u.rol != Rol.ADMIN):
            raise ErrorNegocio("encuesta inexistente", 404)
        return e

    def publica(s: Session, slug: str) -> Encuesta:
        e = s.scalar(select(Encuesta).where(Encuesta.slug == slug))
        if e is None:
            raise ErrorNegocio("encuesta inexistente", 404)
        return e

    @app.post("/encuestas", status_code=201)
    def crear(d: EncuestaIn, u: Usuario = yo, s: Session = S) -> dict:
        e = Encuesta(slug=secrets.token_urlsafe(9), titulo=d.titulo, creador_id=u.id,
                     cierra_en=d.cierra_en.replace(tzinfo=None) if d.cierra_en else None)
        for i, p in enumerate(d.preguntas, start=1):
            servicio.validar_pregunta(p.tipo, p.opciones)
            e.preguntas.append(Pregunta(orden=i, texto=p.texto, tipo=p.tipo, opciones=p.opciones,
                                        obligatoria=p.obligatoria))
        s.add(e)
        s.flush()
        return {"id": e.id, "slug": e.slug, "preguntas": [p.id for p in e.preguntas]}

    @app.post("/encuestas/{eid}/codigos", status_code=201)
    def codigos(eid: int, d: CodigosIn, u: Usuario = yo, s: Session = S) -> dict:
        """Genera códigos de un solo uso. Solo se muestran ahora (se guardan hasheados)."""
        return {"codigos": servicio.generar_codigos(s, propia(s, eid, u), d.cantidad)}

    @app.post("/encuestas/{eid}/cerrar")
    def cerrar(eid: int, u: Usuario = yo, s: Session = S) -> dict:
        propia(s, eid, u).abierta = False
        return {"abierta": False}

    @app.get("/encuestas/{eid}/resultados")
    def resultados(eid: int, u: Usuario = yo, s: Session = S) -> dict:
        return servicio.resultados(s, propia(s, eid, u))

    @app.get("/encuestas/{eid}/resultados.csv")
    def csv(eid: int, u: Usuario = yo, s: Session = S) -> Response:
        return Response(servicio.exportar_csv(s, propia(s, eid, u)), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="encuesta-{eid}.csv"'})

    @app.get("/encuestas/{eid}/preguntas/{pid}/grafico.png")
    def grafico(eid: int, pid: int, u: Usuario = yo, s: Session = S) -> Response:
        res = servicio.resultados(s, propia(s, eid, u))
        item = next((p for p in res["preguntas"] if p["id"] == pid), None)
        if item is None:
            raise ErrorNegocio("pregunta inexistente", 404)
        if "conteo" not in item:
            raise ErrorNegocio("las preguntas de texto no tienen gráfico")
        return Response(graficos.grafico_barras(item["texto"], item["conteo"], item.get("promedio")),
                        media_type="image/png")

    @app.get("/e/{slug}")
    def ver_publica(slug: str, s: Session = S) -> dict:
        """Formulario público (sin datos de resultados)."""
        e = publica(s, slug)
        return {"titulo": e.titulo, "requiere_codigo": e.requiere_codigo, "abierta": e.abierta,
                "preguntas": [{"id": p.id, "texto": p.texto, "tipo": p.tipo.value, "opciones": p.opciones,
                               "obligatoria": p.obligatoria} for p in e.preguntas]}

    @app.post("/e/{slug}/responder", status_code=201)
    def responder(slug: str, d: RespuestaIn, s: Session = S) -> dict:
        servicio.responder(s, publica(s, slug), d.valores, d.codigo, reloj())
        return {"ok": True}  # no se devuelve id: nada que vincule al respondente

    return app


def __getattr__(nombre: str):  # pragma: no cover
    """Atributo perezoso del módulo: ``uvicorn app.main:app`` pide ``app`` y recién ahí se
    crea, así importar el módulo (por ejemplo en los tests) no abre ninguna base.
    """
    if nombre == "app":
        return crear_app()
    raise AttributeError(nombre)
