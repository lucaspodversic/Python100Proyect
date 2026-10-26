"""Reglas de negocio de las reservas, independientes de HTTP.

Separar el servicio de las rutas permite testearlo directamente (incluida la
prueba de concurrencia con varios hilos) y reutilizarlo desde otra interfaz.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from .modelos import EstadoReserva, Habitacion, Reserva, Rol, Usuario

# Límite de noches por reserva (regla de negocio configurable).
MAX_NOCHES = 30


class ErrorNegocio(Exception):
    """Error de regla de negocio. ``codigo`` se traduce a un estado HTTP."""

    def __init__(self, mensaje: str, codigo: int = 400) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo = codigo


def condicion_solapamiento(entrada: date, salida: date):  # type: ignore[no-untyped-def]
    """Condición SQL de solapamiento entre ``[entrada, salida)`` y una reserva.

    Dos intervalos semiabiertos se solapan si cada uno empieza antes de que
    termine el otro: ``existente.entrada < salida AND existente.salida > entrada``.
    Solo cuentan las reservas confirmadas (las canceladas liberan la habitación).
    """
    return and_(
        Reserva.estado == EstadoReserva.CONFIRMADA,
        Reserva.entrada < salida,
        Reserva.salida > entrada,
    )


def habitaciones_disponibles(
    sesion: Session, entrada: date, salida: date, huespedes: int
) -> list[Habitacion]:
    """Lista las habitaciones activas, con capacidad suficiente y sin solapamiento."""
    if salida <= entrada:
        raise ErrorNegocio("rango de fechas inválido")
    # Subconsulta: ids de habitaciones ocupadas en el rango pedido.
    ocupadas = select(Reserva.habitacion_id).where(condicion_solapamiento(entrada, salida))
    consulta = (
        select(Habitacion)
        .where(Habitacion.activa.is_(True))
        .where(Habitacion.capacidad >= huespedes)
        .where(Habitacion.id.not_in(ocupadas))
        .order_by(Habitacion.precio_noche_centavos, Habitacion.numero)
    )
    return list(sesion.scalars(consulta))


def crear_reserva(
    sesion: Session,
    usuario: Usuario,
    habitacion_id: int,
    entrada: date,
    salida: date,
    huespedes: int,
    hoy: date,
) -> Reserva:
    """Crea una reserva validando todas las reglas y sin solapamientos.

    Debe llamarse dentro de una transacción (``sesion.begin()``), que gracias a
    ``BEGIN IMMEDIATE`` serializa las escrituras: la comprobación de
    solapamiento y la inserción no pueden intercalarse con otra reserva.
    """
    if entrada < hoy:
        raise ErrorNegocio("no se puede reservar en el pasado")
    noches = (salida - entrada).days
    if noches <= 0:
        raise ErrorNegocio("la estadía debe ser de al menos una noche")
    if noches > MAX_NOCHES:
        raise ErrorNegocio(f"máximo {MAX_NOCHES} noches por reserva")

    habitacion = sesion.get(Habitacion, habitacion_id)
    if habitacion is None or not habitacion.activa:
        raise ErrorNegocio("habitación inexistente", 404)
    if huespedes > habitacion.capacidad:
        raise ErrorNegocio("la habitación no admite tantos huéspedes")

    # Comprobación de solapamiento dentro de la misma transacción bloqueante.
    conflicto = sesion.scalar(
        select(Reserva.id)
        .where(Reserva.habitacion_id == habitacion_id)
        .where(condicion_solapamiento(entrada, salida))
        .limit(1)
    )
    if conflicto is not None:
        raise ErrorNegocio("la habitación ya está reservada en esas fechas", 409)

    reserva = Reserva(
        habitacion_id=habitacion_id,
        usuario_id=usuario.id,
        entrada=entrada,
        salida=salida,
        huespedes=huespedes,
        total_centavos=noches * habitacion.precio_noche_centavos,
    )
    sesion.add(reserva)
    sesion.flush()  # asigna el id sin cerrar la transacción
    return reserva


def cancelar_reserva(sesion: Session, usuario: Usuario, reserva_id: int, hoy: date) -> Reserva:
    """Cancela una reserva propia (o cualquiera si es admin) antes de la entrada."""
    reserva = sesion.get(Reserva, reserva_id)
    if reserva is None:
        raise ErrorNegocio("reserva inexistente", 404)
    if usuario.rol != Rol.ADMIN and reserva.usuario_id != usuario.id:
        # 404 en vez de 403 para no revelar la existencia de reservas ajenas.
        raise ErrorNegocio("reserva inexistente", 404)
    if reserva.estado == EstadoReserva.CANCELADA:
        raise ErrorNegocio("la reserva ya estaba cancelada", 409)
    if reserva.entrada <= hoy and usuario.rol != Rol.ADMIN:
        raise ErrorNegocio("no se puede cancelar una estadía ya iniciada")
    reserva.estado = EstadoReserva.CANCELADA
    return reserva
