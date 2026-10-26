"""Reglas de negocio de vuelos: búsqueda, asientos, retención, confirmación y precios."""
from __future__ import annotations

import re
import secrets
from datetime import date, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .modelos import AsientoOcupado, EstadoReserva, Reserva, Rol, Usuario, Vuelo

# Minutos que un asiento queda retenido antes de confirmar (simula el tiempo de pago).
MINUTOS_RETENCION = 15
# Alfabeto del PNR sin caracteres ambiguos (0/O, 1/I).
ALFABETO_PNR = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class ErrorNegocio(Exception):
    """Violación de una regla de negocio (``codigo`` = estado HTTP)."""

    def __init__(self, mensaje: str, codigo: int = 400) -> None:
        """``mensaje`` va al cliente como 'detail' y ``codigo`` es el estado HTTP (400 por
        defecto; 404, 409, etc. según el caso).
        """
        super().__init__(mensaje)
        self.mensaje, self.codigo = mensaje, codigo


def asientos_validos(vuelo: Vuelo) -> list[str]:
    """Lista todos los asientos del vuelo: 1A, 1B, ..., 30F."""
    return [f"{fila}{col}" for fila in range(1, vuelo.filas + 1) for col in vuelo.columnas]


def normalizar_asiento(asiento: str) -> str:
    """Normaliza "12c" → "12C" y valida el formato fila+letra."""
    asiento = asiento.strip().upper()
    if not re.fullmatch(r"[1-9][0-9]{0,2}[A-Z]", asiento):
        raise ErrorNegocio("formato de asiento inválido (ej.: 12C)")
    return asiento


def liberar_vencidas(s: Session, ahora: datetime, vuelo_id: int | None = None) -> int:
    """Marca como expiradas las retenciones vencidas y libera sus asientos."""
    consulta = select(Reserva).where(Reserva.estado == EstadoReserva.RETENIDA, Reserva.expira_en <= ahora)
    if vuelo_id is not None:
        consulta = consulta.where(Reserva.vuelo_id == vuelo_id)
    vencidas = list(s.scalars(consulta))
    for r in vencidas:
        r.estado = EstadoReserva.EXPIRADA
        s.execute(delete(AsientoOcupado).where(AsientoOcupado.reserva_id == r.id))
    s.flush()
    return len(vencidas)


def ocupacion(s: Session, vuelo: Vuelo) -> float:
    """Fracción de asientos ocupados (retenidos + vendidos), entre 0 y 1."""
    ocupados = s.scalar(select(func.count()).select_from(AsientoOcupado)
                        .where(AsientoOcupado.vuelo_id == vuelo.id)) or 0
    return ocupados / vuelo.capacidad


def precio_actual(s: Session, vuelo: Vuelo) -> int:
    """Precio dinámico: sube hasta +50 % a medida que el avión se llena.

    ``precio = base × (1 + 0,5 × ocupación)``, redondeado a centavos.
    """
    return round(vuelo.precio_base_centavos * (1 + 0.5 * ocupacion(s, vuelo)))


def buscar(s: Session, origen: str, destino: str, dia: date, ahora: datetime) -> list[Vuelo]:
    """Vuelos de un día entre dos aeropuertos que todavía no salieron."""
    inicio = datetime.combine(dia, datetime.min.time())
    return list(s.scalars(select(Vuelo).where(
        Vuelo.origen == origen.upper(), Vuelo.destino == destino.upper(),
        Vuelo.salida >= max(inicio, ahora), Vuelo.salida < inicio + timedelta(days=1)
    ).order_by(Vuelo.salida)))


def mapa_asientos(s: Session, vuelo: Vuelo, ahora: datetime) -> dict[str, bool]:
    """Devuelve ``{asiento: libre?}`` para todo el avión."""
    liberar_vencidas(s, ahora, vuelo.id)
    ocupados = set(s.scalars(select(AsientoOcupado.asiento).where(AsientoOcupado.vuelo_id == vuelo.id)))
    return {a: a not in ocupados for a in asientos_validos(vuelo)}


def retener(s: Session, usuario: Usuario, vuelo_id: int, asiento: str, pasajero: str,
            ahora: datetime) -> Reserva:
    """Retiene un asiento durante ``MINUTOS_RETENCION`` minutos.

    La unicidad la garantiza la PK de ``AsientoOcupado``: si otro proceso tomó
    el asiento un instante antes, el ``flush`` falla y se responde 409.
    """
    vuelo = s.get(Vuelo, vuelo_id)
    if vuelo is None:
        raise ErrorNegocio("vuelo inexistente", 404)
    if vuelo.salida <= ahora:
        raise ErrorNegocio("el vuelo ya salió")
    asiento = normalizar_asiento(asiento)
    if asiento not in asientos_validos(vuelo):
        raise ErrorNegocio("ese asiento no existe en el avión")
    if not pasajero.strip():
        raise ErrorNegocio("falta el nombre del pasajero")
    liberar_vencidas(s, ahora, vuelo.id)
    precio = precio_actual(s, vuelo)  # se congela el precio al momento de retener
    reserva = Reserva(pnr="".join(secrets.choice(ALFABETO_PNR) for _ in range(6)),
                      vuelo_id=vuelo.id, usuario_id=usuario.id, asiento=asiento,
                      pasajero=pasajero.strip(), precio_centavos=precio,
                      estado=EstadoReserva.RETENIDA,
                      expira_en=ahora + timedelta(minutes=MINUTOS_RETENCION))
    s.add(reserva)
    s.flush()
    try:
        # SAVEPOINT: si falla el candado, deshacemos solo esta parte.
        with s.begin_nested():
            s.add(AsientoOcupado(vuelo_id=vuelo.id, asiento=asiento, reserva_id=reserva.id))
    except IntegrityError:
        raise ErrorNegocio("el asiento ya está ocupado", 409) from None
    return reserva


def _reserva_de(s: Session, pnr: str, usuario: Usuario) -> Reserva:
    """Obtiene una reserva por PNR verificando que sea del usuario (o admin)."""
    r = s.scalar(select(Reserva).where(Reserva.pnr == pnr.upper()))
    if r is None or (usuario.rol != Rol.ADMIN and r.usuario_id != usuario.id):
        raise ErrorNegocio("reserva inexistente", 404)
    return r


def confirmar(s: Session, usuario: Usuario, pnr: str, ahora: datetime) -> Reserva:
    """Confirma (simula el pago) una retención vigente."""
    r = _reserva_de(s, pnr, usuario)
    liberar_vencidas(s, ahora, r.vuelo_id)
    if r.estado == EstadoReserva.EXPIRADA:
        raise ErrorNegocio("la retención expiró; volvé a elegir asiento", 409)
    if r.estado != EstadoReserva.RETENIDA:
        raise ErrorNegocio(f"la reserva está {r.estado.value}", 409)
    r.estado = EstadoReserva.CONFIRMADA
    r.expira_en = None
    return r


def cancelar(s: Session, usuario: Usuario, pnr: str) -> Reserva:
    """Cancela una reserva retenida o confirmada y libera el asiento."""
    r = _reserva_de(s, pnr, usuario)
    if r.estado not in (EstadoReserva.RETENIDA, EstadoReserva.CONFIRMADA):
        raise ErrorNegocio(f"la reserva está {r.estado.value}", 409)
    r.estado = EstadoReserva.CANCELADA
    s.execute(delete(AsientoOcupado).where(AsientoOcupado.reserva_id == r.id))
    return r
