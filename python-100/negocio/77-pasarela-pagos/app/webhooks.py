"""Firma y verificación de webhooks con HMAC-SHA256.

Formato de la cabecera (inspirado en el estándar de facto de la industria):

    Firma-Pasarela: t=<unix_timestamp>,v1=<hex HMAC-SHA256(secreto, "<t>.<cuerpo>")>

- Incluir el *timestamp* en lo firmado impide reutilizar una firma vieja
  (ataque de repetición) si el receptor aplica una tolerancia.
- La comparación usa ``hmac.compare_digest`` (tiempo constante).

Este módulo no depende de FastAPI: un comercio puede copiarlo para verificar
los webhooks que recibe.
"""
from __future__ import annotations

import hashlib
import hmac

TOLERANCIA_SEG = 300  # 5 minutos


def firmar(secreto: str, cuerpo: bytes, timestamp: int) -> str:
    """Devuelve el valor completo de la cabecera de firma."""
    mac = hmac.new(secreto.encode(), f"{timestamp}.".encode() + cuerpo, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={mac}"


def verificar(secreto: str, cuerpo: bytes, cabecera: str, ahora: int, tolerancia: int = TOLERANCIA_SEG) -> bool:
    """``True`` si la firma es válida y el timestamp está dentro de la tolerancia."""
    try:
        partes = dict(p.split("=", 1) for p in cabecera.split(","))
        t = int(partes["t"])
        recibida = partes["v1"]
    except (ValueError, KeyError):
        return False  # cabecera mal formada
    if abs(ahora - t) > tolerancia:
        return False  # demasiado vieja (o del futuro): posible repetición
    esperada = firmar(secreto, cuerpo, t).split("v1=", 1)[1]
    return hmac.compare_digest(esperada, recibida)
