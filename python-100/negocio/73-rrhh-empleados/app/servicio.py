"""Reglas de negocio de RRHH: ausencias, saldo de vacaciones y liquidación."""
from __future__ import annotations

from datetime import date

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import nomina
from .modelos import Ausencia, Empleado, EstadoAusencia, Nomina, TipoAusencia, Usuario


class ErrorNegocio(Exception):
    """Violación de una regla de negocio (``codigo`` = estado HTTP sugerido)."""

    def __init__(self, mensaje: str, codigo: int = 400) -> None:
        """``mensaje`` va al cliente como 'detail' y ``codigo`` es el estado HTTP (400 por
        defecto; 404, 409, etc. según el caso).
        """
        super().__init__(mensaje)
        self.mensaje, self.codigo = mensaje, codigo


ACTIVAS = (EstadoAusencia.SOLICITADA, EstadoAusencia.APROBADA)


def dias_vacaciones_usados(sesion: Session, empleado_id: int, anio: int) -> int:
    """Suma los días de vacaciones solicitadas o aprobadas que empiezan en ``anio``."""
    ausencias = sesion.scalars(select(Ausencia).where(
        Ausencia.empleado_id == empleado_id, Ausencia.tipo == TipoAusencia.VACACIONES,
        Ausencia.estado.in_(ACTIVAS),
        Ausencia.desde >= date(anio, 1, 1), Ausencia.desde <= date(anio, 12, 31)))
    return sum(a.dias for a in ausencias)


def solicitar_ausencia(sesion: Session, empleado: Empleado, tipo: TipoAusencia,
                       desde: date, hasta: date) -> Ausencia:
    """Registra una solicitud validando fechas, solapamiento y saldo de vacaciones."""
    if hasta < desde:
        raise ErrorNegocio("'hasta' no puede ser anterior a 'desde'")
    if not empleado.activo:
        raise ErrorNegocio("empleado dado de baja")
    # Solapamiento con intervalos cerrados: a.desde <= hasta AND a.hasta >= desde.
    choque = sesion.scalar(select(Ausencia.id).where(and_(
        Ausencia.empleado_id == empleado.id, Ausencia.estado.in_(ACTIVAS),
        Ausencia.desde <= hasta, Ausencia.hasta >= desde)).limit(1))
    if choque is not None:
        raise ErrorNegocio("se solapa con otra ausencia", 409)
    nueva = Ausencia(empleado_id=empleado.id, tipo=tipo, desde=desde, hasta=hasta)
    if tipo == TipoAusencia.VACACIONES:
        usados = dias_vacaciones_usados(sesion, empleado.id, desde.year)
        if usados + nueva.dias > empleado.dias_vacaciones_anuales:
            disponibles = empleado.dias_vacaciones_anuales - usados
            raise ErrorNegocio(f"saldo insuficiente: quedan {disponibles} días", 409)
    sesion.add(nueva)
    sesion.flush()
    return nueva


def resolver_ausencia(sesion: Session, ausencia_id: int, aprobador: Usuario, aprobar: bool) -> Ausencia:
    """Aprueba o rechaza una solicitud. Nadie puede resolver la propia."""
    a = sesion.get(Ausencia, ausencia_id)
    if a is None:
        raise ErrorNegocio("ausencia inexistente", 404)
    if a.estado != EstadoAusencia.SOLICITADA:
        raise ErrorNegocio("la solicitud ya fue resuelta", 409)
    if a.empleado.usuario_id == aprobador.id:
        raise ErrorNegocio("no podés aprobar tu propia ausencia", 403)
    a.estado = EstadoAusencia.APROBADA if aprobar else EstadoAusencia.RECHAZADA
    a.resuelta_por = aprobador.id
    return a


def liquidar_periodo(sesion: Session, periodo: str) -> list[Nomina]:
    """Liquida la nómina de todos los empleados activos para ``AAAA-MM``.

    Es idempotente a nivel de BD: si el período ya se liquidó, la restricción
    única lo impide y se devuelve 409 (no se duplican pagos).
    """
    try:
        nomina.rango_periodo(periodo)
    except (ValueError, TypeError):
        raise ErrorNegocio("período inválido, formato AAAA-MM") from None
    resultado = []
    for emp in sesion.scalars(select(Empleado).where(Empleado.activo.is_(True)).order_by(Empleado.legajo)):
        sin_goce = sesion.scalars(select(Ausencia).where(
            Ausencia.empleado_id == emp.id, Ausencia.tipo == TipoAusencia.SIN_GOCE,
            Ausencia.estado == EstadoAusencia.APROBADA))
        dias = sum(nomina.dias_en_periodo(a.desde, a.hasta, periodo) for a in sin_goce)
        liq = nomina.liquidar(emp.salario_bruto_centavos, dias)
        n = Nomina(empleado_id=emp.id, periodo=periodo, bruto_centavos=liq.bruto,
                   descuento_ausencias_centavos=liq.descuento_ausencias,
                   aportes_centavos=liq.aportes, neto_centavos=liq.neto)
        sesion.add(n)
        resultado.append(n)
    try:
        sesion.flush()
    except IntegrityError:
        raise ErrorNegocio("el período ya fue liquidado", 409) from None
    return resultado


def masa_salarial_por_departamento(sesion: Session) -> dict[str, int]:
    """Suma de salarios brutos de empleados activos agrupada por departamento."""
    filas = sesion.execute(select(Empleado.departamento, func.sum(Empleado.salario_bruto_centavos))
                           .where(Empleado.activo.is_(True)).group_by(Empleado.departamento))
    return {d: int(t) for d, t in filas}
