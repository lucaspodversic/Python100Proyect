"""Lógica de la pasarela: pagos, reembolsos, idempotencia y despacho de webhooks."""
from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import tarjetas, webhooks
from .modelos import ClaveIdempotencia, ConfigWebhook, EstadoPago, Evento, Pago, Reembolso, Usuario

MONEDAS = {"ARS", "USD", "EUR"}
MAX_INTENTOS_WEBHOOK = 5

#: Firma del transporte HTTP: (url, cabeceras, cuerpo) -> código de estado.
Transporte = Callable[[str, dict[str, str], bytes], int]


class ErrorNegocio(Exception):
    def __init__(self, mensaje: str, codigo: int = 400) -> None:
        super().__init__(mensaje)
        self.mensaje, self.codigo = mensaje, codigo


def id_publico(prefijo: str) -> str:
    """Identificador opaco no secuencial (no revela volumen de operaciones)."""
    return f"{prefijo}_{secrets.token_hex(12)}"


# ---------------------------------------------------------------- idempotencia
def huella(ruta: str, cuerpo: Any) -> str:
    """SHA-256 de la ruta y el cuerpo canónico (JSON con claves ordenadas)."""
    return hashlib.sha256((ruta + json.dumps(cuerpo, sort_keys=True)).encode()).hexdigest()


def con_idempotencia(s: Session, comercio: Usuario, clave: str, huella_peticion: str, ahora: datetime,
                     operacion: Callable[[], tuple[int, dict]]) -> tuple[int, dict, bool]:
    """Ejecuta ``operacion`` como mucho una vez por (comercio, clave).

    Devuelve ``(codigo, respuesta, repetida)``:

    - Clave nueva → se ejecuta y se guarda la respuesta.
    - Clave conocida con la misma petición → se devuelve la respuesta guardada.
    - Clave conocida con *otra* petición → 422 (uso incorrecto de la clave).

    La transacción se abre con ``BEGIN IMMEDIATE`` (ver ``db.py``), así que
    dos peticiones simultáneas con la misma clave se serializan; además la
    restricción ``UNIQUE(comercio_id, clave)`` actúa como red de seguridad.
    Los errores de negocio no se guardan: la transacción se revierte y el
    cliente puede reintentar con la misma clave.
    """
    if not 8 <= len(clave) <= 100:
        raise ErrorNegocio("Idempotency-Key debe tener entre 8 y 100 caracteres")
    previa = s.scalar(select(ClaveIdempotencia).where(ClaveIdempotencia.comercio_id == comercio.id,
                                                     ClaveIdempotencia.clave == clave))
    if previa is not None:
        if previa.huella != huella_peticion:
            raise ErrorNegocio("la Idempotency-Key ya se usó con otra petición", 422)
        return previa.codigo, json.loads(previa.respuesta), True
    codigo, respuesta = operacion()
    s.add(ClaveIdempotencia(comercio_id=comercio.id, clave=clave, huella=huella_peticion,
                            codigo=codigo, respuesta=json.dumps(respuesta), creado=ahora))
    s.flush()
    return codigo, respuesta, False


# ---------------------------------------------------------------- serialización
def pago_dict(p: Pago) -> dict:
    return {"id": p.publico, "monto_centavos": p.monto_centavos, "moneda": p.moneda, "estado": p.estado.value,
            "motivo_rechazo": p.motivo_rechazo, "tarjeta": {"marca": p.marca, "ultimos4": p.ultimos4},
            "reembolsado_centavos": p.reembolsado_centavos, "descripcion": p.descripcion}


# ---------------------------------------------------------------- eventos
def emitir(s: Session, comercio_id: int, tipo: str, datos: dict) -> Evento:
    """Encola un evento (patrón *outbox*: se guarda en la misma transacción que el cambio)."""
    publico = id_publico("evt")
    cuerpo = json.dumps({"id": publico, "tipo": tipo, "datos": datos}, sort_keys=True)
    ev = Evento(publico=publico, comercio_id=comercio_id, tipo=tipo, cuerpo=cuerpo)
    s.add(ev)
    return ev


def despachar(s: Session, comercio_id: int, transporte: Transporte, ahora_unix: int) -> dict[str, int]:
    """Intenta entregar los eventos pendientes de un comercio, firmados con HMAC."""
    config = s.get(ConfigWebhook, comercio_id)
    if config is None:
        raise ErrorNegocio("el comercio no configuró webhooks", 409)
    pendientes = s.scalars(select(Evento).where(Evento.comercio_id == comercio_id, Evento.entregado.is_(False),
                                                Evento.intentos < MAX_INTENTOS_WEBHOOK).order_by(Evento.id))
    resumen = {"entregados": 0, "fallidos": 0}
    for ev in pendientes:
        cuerpo = ev.cuerpo.encode()
        cabeceras = {"Content-Type": "application/json",
                     "Firma-Pasarela": webhooks.firmar(config.secreto, cuerpo, ahora_unix)}
        ev.intentos += 1
        try:
            estado = transporte(config.url, cabeceras, cuerpo)
            ok, error = 200 <= estado < 300, f"HTTP {estado}"
        except Exception as e:  # noqa: BLE001 - cualquier fallo de red cuenta como intento fallido
            ok, error = False, type(e).__name__
        ev.entregado = ok
        ev.ultimo_error = None if ok else error
        resumen["entregados" if ok else "fallidos"] += 1
    return resumen


# ---------------------------------------------------------------- pagos
def cobrar(s: Session, comercio: Usuario, monto: int, moneda: str, numero: str, mes: int, anio: int,
           descripcion: str, ahora: datetime) -> tuple[int, dict]:
    """Crea un pago (aprobado → 201, rechazado → 402). Ambos quedan registrados."""
    moneda = moneda.upper()
    if moneda not in MONEDAS:
        raise ErrorNegocio(f"moneda no soportada: {moneda}")
    res = tarjetas.procesar(numero, mes, anio, (ahora.year, ahora.month))
    pago = Pago(publico=id_publico("pay"), comercio_id=comercio.id, monto_centavos=monto, moneda=moneda,
                estado=EstadoPago.APROBADO if res.aprobado else EstadoPago.RECHAZADO,
                motivo_rechazo=res.motivo, ultimos4=res.ultimos4, marca=res.marca,
                descripcion=descripcion, creado=ahora)
    s.add(pago)
    s.flush()
    datos = pago_dict(pago)
    emitir(s, comercio.id, "pago.aprobado" if res.aprobado else "pago.rechazado", datos)
    return (201 if res.aprobado else 402), datos


def pago_de(s: Session, comercio: Usuario, publico: str) -> Pago:
    """Pago del comercio (404 si no existe o es de otro comercio)."""
    p = s.scalar(select(Pago).where(Pago.publico == publico))
    if p is None or p.comercio_id != comercio.id:
        raise ErrorNegocio("pago inexistente", 404)
    return p


def reembolsar(s: Session, comercio: Usuario, publico: str, monto: int | None, motivo: str,
               ahora: datetime) -> tuple[int, dict]:
    """Reembolso total o parcial. La suma de reembolsos nunca supera el pago."""
    p = pago_de(s, comercio, publico)
    if p.estado == EstadoPago.RECHAZADO:
        raise ErrorNegocio("no se puede reembolsar un pago rechazado", 409)
    disponible = p.monto_centavos - p.reembolsado_centavos
    monto = disponible if monto is None else monto
    if monto <= 0 or monto > disponible:
        raise ErrorNegocio(f"monto inválido: disponible para reembolsar {disponible}", 409)
    p.reembolsado_centavos += monto
    p.estado = EstadoPago.REEMBOLSADO if p.reembolsado_centavos == p.monto_centavos else EstadoPago.REEMBOLSADO_PARCIAL
    r = Reembolso(publico=id_publico("re"), pago_id=p.id, monto_centavos=monto, motivo=motivo, creado=ahora)
    s.add(r)
    s.flush()
    datos = {"id": r.publico, "pago": p.publico, "monto_centavos": monto, "estado_pago": p.estado.value}
    emitir(s, comercio.id, "reembolso.creado", datos)
    return 201, datos
