"""Reglas de negocio: autoría, inscripción, progreso y corrección de exámenes."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .modelos import (Curso, Examen, Inscripcion, Intento, Leccion, LeccionCompletada,
                      Rol, Usuario)


class ErrorNegocio(Exception):
    """Violación de una regla de negocio (``codigo`` = estado HTTP)."""

    def __init__(self, mensaje: str, codigo: int = 400) -> None:
        """``mensaje`` va al cliente como 'detail' y ``codigo`` es el estado HTTP (400 por
        defecto; 404, 409, etc. según el caso).
        """
        super().__init__(mensaje)
        self.mensaje, self.codigo = mensaje, codigo


def curso_propio(s: Session, curso_id: int, usuario: Usuario) -> Curso:
    """Devuelve el curso si el usuario es su profesor (o admin)."""
    curso = s.get(Curso, curso_id)
    if curso is None:
        raise ErrorNegocio("curso inexistente", 404)
    if usuario.rol != Rol.ADMIN and curso.profesor_id != usuario.id:
        raise ErrorNegocio("solo el profesor del curso puede modificarlo", 403)
    return curso


def validar_preguntas(preguntas: list[dict]) -> None:
    """Comprueba que cada pregunta tenga ≥2 opciones y una respuesta correcta válida."""
    if not preguntas:
        raise ErrorNegocio("el examen necesita al menos una pregunta")
    for i, p in enumerate(preguntas, 1):
        opciones = p.get("opciones", [])
        if len(opciones) < 2:
            raise ErrorNegocio(f"pregunta {i}: mínimo 2 opciones")
        if not isinstance(p.get("correcta"), int) or not 0 <= p["correcta"] < len(opciones):
            raise ErrorNegocio(f"pregunta {i}: índice de respuesta correcta inválido")


def publicar(s: Session, curso: Curso) -> Curso:
    """Publica el curso; exige al menos una lección."""
    if not curso.lecciones:
        raise ErrorNegocio("no se puede publicar un curso sin lecciones")
    curso.publicado = True
    return curso


def inscribir(s: Session, curso_id: int, alumno: Usuario) -> Inscripcion:
    """Inscribe a un alumno en un curso publicado (una sola vez)."""
    curso = s.get(Curso, curso_id)
    if curso is None or not curso.publicado:
        raise ErrorNegocio("curso no disponible", 404)
    if s.scalar(select(Inscripcion).where(Inscripcion.curso_id == curso_id, Inscripcion.alumno_id == alumno.id)):
        raise ErrorNegocio("ya estás inscripto", 409)
    insc = Inscripcion(curso_id=curso_id, alumno_id=alumno.id)
    s.add(insc)
    s.flush()
    return insc


def exigir_inscripcion(s: Session, curso_id: int, alumno: Usuario) -> None:
    """Lanza 403 si el alumno no está inscripto en el curso."""
    if s.scalar(select(Inscripcion.id).where(Inscripcion.curso_id == curso_id,
                                             Inscripcion.alumno_id == alumno.id)) is None:
        raise ErrorNegocio("no estás inscripto en este curso", 403)


def completar_leccion(s: Session, leccion_id: int, alumno: Usuario) -> None:
    """Marca una lección como completada (repetir no duplica)."""
    leccion = s.get(Leccion, leccion_id)
    if leccion is None:
        raise ErrorNegocio("lección inexistente", 404)
    exigir_inscripcion(s, leccion.curso_id, alumno)
    ya = s.scalar(select(LeccionCompletada.id).where(LeccionCompletada.leccion_id == leccion_id,
                                                     LeccionCompletada.alumno_id == alumno.id))
    if ya is None:
        s.add(LeccionCompletada(leccion_id=leccion_id, alumno_id=alumno.id))
        s.flush()


def corregir(preguntas: list[dict], respuestas: list[int]) -> int:
    """Devuelve la nota 0-100 (redondeo hacia abajo) comparando con las correctas."""
    if len(respuestas) != len(preguntas):
        raise ErrorNegocio("hay que responder todas las preguntas")
    aciertos = sum(1 for p, r in zip(preguntas, respuestas) if p["correcta"] == r)
    return aciertos * 100 // len(preguntas)


def rendir_examen(s: Session, curso_id: int, alumno: Usuario, respuestas: list[int]) -> Intento:
    """Registra un intento respetando el máximo de intentos y si ya aprobó."""
    exigir_inscripcion(s, curso_id, alumno)
    examen = s.scalar(select(Examen).where(Examen.curso_id == curso_id))
    if examen is None:
        raise ErrorNegocio("el curso no tiene examen", 404)
    previos = list(s.scalars(select(Intento).where(Intento.examen_id == examen.id, Intento.alumno_id == alumno.id)))
    if any(i.aprobado for i in previos):
        raise ErrorNegocio("ya aprobaste este examen", 409)
    if len(previos) >= examen.max_intentos:
        raise ErrorNegocio("agotaste los intentos", 409)
    nota = corregir(examen.preguntas, respuestas)
    intento = Intento(examen_id=examen.id, alumno_id=alumno.id, respuestas=respuestas,
                      nota=nota, aprobado=nota >= examen.nota_aprobacion)
    s.add(intento)
    s.flush()
    return intento


def progreso(s: Session, curso_id: int, alumno: Usuario) -> dict:
    """Porcentaje de lecciones completadas, estado del examen y certificado."""
    exigir_inscripcion(s, curso_id, alumno)
    curso = s.get(Curso, curso_id)
    total = len(curso.lecciones)
    hechas = s.scalar(select(func.count()).select_from(LeccionCompletada).join(Leccion)
                      .where(Leccion.curso_id == curso_id, LeccionCompletada.alumno_id == alumno.id)) or 0
    aprobado = False
    if curso.examen is not None:
        aprobado = s.scalar(select(Intento.id).where(Intento.examen_id == curso.examen.id,
                                                     Intento.alumno_id == alumno.id,
                                                     Intento.aprobado.is_(True))) is not None
    porcentaje = hechas * 100 // total if total else 0
    # Certificado: todas las lecciones y, si existe examen, aprobado.
    certificado = porcentaje == 100 and (curso.examen is None or aprobado)
    return {"lecciones_completadas": hechas, "lecciones_totales": total,
            "porcentaje": porcentaje, "examen_aprobado": aprobado, "certificado": certificado}
