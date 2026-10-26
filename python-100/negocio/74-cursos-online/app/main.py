"""API de la plataforma de cursos.

- Profesores: crean cursos, lecciones y examen; publican; ven inscriptos.
- Alumnos: catálogo, inscripción, lecciones (solo si están inscriptos),
  completar lecciones, rendir examen y ver su progreso.
"""
from __future__ import annotations

import os

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import servicio
from .auth import crear_auth, crear_usuario
from .db import Base, crear_fabrica_sesiones, crear_motor
from .modelos import Curso, Examen, Inscripcion, Leccion, Rol, Token, Usuario


class CursoIn(BaseModel):
    """Alta de curso: título de 3 a 200 caracteres y descripción opcional. Nace sin publicar."""
    titulo: str = Field(min_length=3, max_length=200)
    descripcion: str = Field(default="", max_length=5000)


class LeccionIn(BaseModel):
    """Lección: ``orden`` >= 1, único dentro del curso (la base lo garantiza con una
    restricción UNIQUE).
    """
    orden: int = Field(ge=1)
    titulo: str = Field(min_length=1, max_length=200)
    contenido: str = Field(min_length=1)


class PreguntaIn(BaseModel):
    """Pregunta de opción múltiple: ``correcta`` es el índice (desde 0) de la opción correcta.
    La validación de fondo (al menos 2 opciones, índice en rango) la hace el servicio.
    """
    enunciado: str = Field(min_length=1)
    opciones: list[str]
    correcta: int


class ExamenIn(BaseModel):
    """Examen del curso: preguntas, nota mínima de aprobación (1-100, 60 por defecto) e
    intentos permitidos (1-10, 3 por defecto).
    """
    preguntas: list[PreguntaIn]
    nota_aprobacion: int = Field(default=60, ge=1, le=100)
    max_intentos: int = Field(default=3, ge=1, le=10)


class RespuestasIn(BaseModel):
    """Un intento: el índice elegido para cada pregunta, en orden."""
    respuestas: list[int]


class RolIn(BaseModel):
    """Cambio de rol (solo admin): alumno, profesor o admin."""
    rol: Rol


def _curso_dict(c: Curso) -> dict:
    """Serialización pública de un curso (sin contenido de lecciones)."""
    return {"id": c.id, "titulo": c.titulo, "descripcion": c.descripcion,
            "profesor_id": c.profesor_id, "publicado": c.publicado, "lecciones": len(c.lecciones)}


def crear_app(url_bd: str = "sqlite:///cursos.db", admin_email: str = "admin@cursos.local",
              admin_password: str | None = None) -> FastAPI:
    """Fábrica de la aplicación."""
    app = FastAPI(title="Cursos online", version="1.0.0")
    motor = crear_motor(url_bd)
    Base.metadata.create_all(motor)
    fabrica = crear_fabrica_sesiones(motor)
    password = admin_password or os.environ.get("CURSOS_ADMIN_PASSWORD")
    if password:
        with fabrica.begin() as s:
            if s.scalar(select(Usuario).where(Usuario.email == admin_email)) is None:
                crear_usuario(s, Usuario, admin_email, "Admin", password, Rol.ADMIN)

    auth = crear_auth(fabrica, Usuario, Token, Rol.ALUMNO)
    app.include_router(auth.router)
    S = Depends(auth.obtener_sesion)
    profesor = Depends(auth.requiere_rol(Rol.PROFESOR, Rol.ADMIN))
    alumno = Depends(auth.requiere_rol(Rol.ALUMNO))
    admin = Depends(auth.requiere_rol(Rol.ADMIN))

    @app.exception_handler(servicio.ErrorNegocio)
    async def _err(_r: Request, e: servicio.ErrorNegocio) -> JSONResponse:
        """Traduce ErrorNegocio a una respuesta JSON con su código y {'detail': mensaje}, el
        mismo formato que usan las HTTPException de FastAPI.
        """
        return JSONResponse(status_code=e.codigo, content={"detail": e.mensaje})

    @app.patch("/usuarios/{uid}/rol", dependencies=[admin])
    def cambiar_rol(uid: int, d: RolIn, s: Session = S) -> dict:
        """Admin: cambia el rol de un usuario (así se crean profesores, porque el registro
        siempre da 'alumno').
        """
        u = s.get(Usuario, uid)
        if u is None:
            raise HTTPException(404, "usuario inexistente")
        u.rol = d.rol
        return {"id": uid, "rol": d.rol.value}

    # ---------- Profesor ----------
    @app.post("/cursos", status_code=201)
    def crear_curso(d: CursoIn, u: Usuario = profesor, s: Session = S) -> dict:
        """Profesor: crea un curso propio, sin publicar."""
        c = Curso(titulo=d.titulo, descripcion=d.descripcion, profesor_id=u.id)
        s.add(c)
        s.flush()
        return _curso_dict(c)

    @app.post("/cursos/{cid}/lecciones", status_code=201)
    def agregar_leccion(cid: int, d: LeccionIn, u: Usuario = profesor, s: Session = S) -> dict:
        """Profesor dueño: agrega una lección. Un orden repetido choca con la restricción
        UNIQUE y se informa como 409 en lugar de un 500.
        """
        curso = servicio.curso_propio(s, cid, u)
        leccion = Leccion(curso_id=curso.id, **d.model_dump())
        s.add(leccion)
        try:
            s.flush()
        except IntegrityError:
            raise HTTPException(409, "ya existe una lección con ese orden") from None
        s.refresh(curso)
        return {"id": leccion.id, "orden": leccion.orden}

    @app.put("/cursos/{cid}/examen")
    def definir_examen(cid: int, d: ExamenIn, u: Usuario = profesor, s: Session = S) -> dict:
        """Profesor dueño: crea o reemplaza el examen (PUT idempotente). Las preguntas se
        validan antes de guardar.
        """
        curso = servicio.curso_propio(s, cid, u)
        preguntas = [p.model_dump() for p in d.preguntas]
        servicio.validar_preguntas(preguntas)
        if curso.examen is None:
            curso.examen = Examen(preguntas=preguntas, nota_aprobacion=d.nota_aprobacion,
                                  max_intentos=d.max_intentos)
        else:
            curso.examen.preguntas = preguntas
            curso.examen.nota_aprobacion = d.nota_aprobacion
            curso.examen.max_intentos = d.max_intentos
        return {"preguntas": len(preguntas)}

    @app.post("/cursos/{cid}/publicar")
    def publicar(cid: int, u: Usuario = profesor, s: Session = S) -> dict:
        """Profesor dueño: publica el curso (el servicio exige al menos una lección)."""
        return _curso_dict(servicio.publicar(s, servicio.curso_propio(s, cid, u)))

    @app.get("/cursos/{cid}/inscriptos")
    def inscriptos(cid: int, u: Usuario = profesor, s: Session = S) -> dict:
        """Profesor dueño: cantidad de alumnos inscriptos."""
        servicio.curso_propio(s, cid, u)
        n = s.scalar(select(func.count()).select_from(Inscripcion).where(Inscripcion.curso_id == cid))
        return {"curso_id": cid, "inscriptos": n}

    # ---------- Público / alumno ----------
    @app.get("/cursos")
    def catalogo(s: Session = S) -> list[dict]:
        """Catálogo público: solo cursos publicados."""
        return [_curso_dict(c) for c in s.scalars(select(Curso).where(Curso.publicado.is_(True)).order_by(Curso.id))]

    @app.post("/cursos/{cid}/inscripcion", status_code=201)
    def inscribirse(cid: int, u: Usuario = alumno, s: Session = S) -> dict:
        """Alumno: se inscribe en un curso publicado (404 si no está publicado, 409 si ya
        estaba inscripto).
        """
        servicio.inscribir(s, cid, u)
        return {"curso_id": cid, "inscripto": True}

    @app.get("/cursos/{cid}/lecciones")
    def ver_lecciones(cid: int, u: Usuario = alumno, s: Session = S) -> list[dict]:
        """Alumno inscripto: lecciones con su contenido, en orden."""
        servicio.exigir_inscripcion(s, cid, u)
        curso = s.get(Curso, cid)
        return [{"id": l.id, "orden": l.orden, "titulo": l.titulo, "contenido": l.contenido} for l in curso.lecciones]

    @app.post("/lecciones/{lid}/completar")
    def completar(lid: int, u: Usuario = alumno, s: Session = S) -> dict:
        """Alumno inscripto: marca una lección como completada (idempotente)."""
        servicio.completar_leccion(s, lid, u)
        return {"leccion_id": lid, "completada": True}

    @app.get("/cursos/{cid}/examen")
    def ver_examen(cid: int, u: Usuario = alumno, s: Session = S) -> dict:
        """Preguntas sin la respuesta correcta (nunca se expone al alumno)."""
        servicio.exigir_inscripcion(s, cid, u)
        examen = s.scalar(select(Examen).where(Examen.curso_id == cid))
        if examen is None:
            raise HTTPException(404, "sin examen")
        return {"preguntas": [{"enunciado": p["enunciado"], "opciones": p["opciones"]} for p in examen.preguntas],
                "max_intentos": examen.max_intentos}

    @app.post("/cursos/{cid}/examen/intentos", status_code=201)
    def rendir(cid: int, d: RespuestasIn, u: Usuario = alumno, s: Session = S) -> dict:
        """Alumno inscripto: rinde el examen y devuelve nota y si aprobó."""
        i = servicio.rendir_examen(s, cid, u, d.respuestas)
        return {"nota": i.nota, "aprobado": i.aprobado}

    @app.get("/cursos/{cid}/progreso")
    def progreso(cid: int, u: Usuario = alumno, s: Session = S) -> dict:
        """Alumno: porcentaje de lecciones completadas y si ya tiene el certificado (100 % de
        lecciones + examen aprobado).
        """
        return servicio.progreso(s, cid, u)

    return app


def __getattr__(nombre: str):  # pragma: no cover - instancia perezosa para uvicorn
    """Atributo perezoso del módulo: ``uvicorn app.main:app`` pide ``app`` y recién ahí se
    crea, así importar el módulo (por ejemplo en los tests) no abre ninguna base.
    """
    if nombre == "app":
        return crear_app()
    raise AttributeError(nombre)
