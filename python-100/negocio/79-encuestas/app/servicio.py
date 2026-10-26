"""Lógica de encuestas: validación de respuestas, códigos y agregación."""
from __future__ import annotations

import csv
import hashlib
import io
import secrets
from collections import Counter
from datetime import datetime
from statistics import mean
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .modelos import Codigo, Encuesta, Pregunta, Respuesta, TipoPregunta

ESCALA_MIN, ESCALA_MAX = 1, 5


class ErrorNegocio(Exception):
    def __init__(self, mensaje: str, codigo: int = 400) -> None:
        """``mensaje`` va al cliente como 'detail' y ``codigo`` es el estado HTTP (400 por
        defecto; 404, 409, etc. según el caso).
        """
        super().__init__(mensaje)
        self.mensaje, self.codigo = mensaje, codigo


def hash_codigo(codigo: str) -> str:
    return hashlib.sha256(codigo.strip().upper().encode()).hexdigest()


def generar_codigos(s: Session, encuesta: Encuesta, cantidad: int) -> list[str]:
    """Genera códigos legibles (8 caracteres). Se devuelven una única vez."""
    alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    codigos = ["".join(secrets.choice(alfabeto) for _ in range(8)) for _ in range(cantidad)]
    s.add_all(Codigo(encuesta_id=encuesta.id, codigo_hash=hash_codigo(c)) for c in codigos)
    encuesta.requiere_codigo = True
    return codigos


def validar_pregunta(tipo: TipoPregunta, opciones: list[str]) -> None:
    """Coherencia de la definición: las de opciones necesitan ≥2 opciones únicas."""
    if tipo in (TipoPregunta.UNICA, TipoPregunta.MULTIPLE):
        if len(opciones) < 2 or len(set(opciones)) != len(opciones):
            raise ErrorNegocio("las preguntas de opciones requieren al menos 2 opciones distintas")
    elif opciones:
        raise ErrorNegocio(f"las preguntas de tipo {tipo.value} no llevan opciones")


def validar_valor(p: Pregunta, valor: Any) -> Any:
    """Valida y normaliza la respuesta a una pregunta según su tipo."""
    if p.tipo == TipoPregunta.UNICA:
        if valor not in p.opciones:
            raise ErrorNegocio(f"pregunta {p.orden}: opción inválida")
        return valor
    if p.tipo == TipoPregunta.MULTIPLE:
        if not isinstance(valor, list) or not valor or any(v not in p.opciones for v in valor):
            raise ErrorNegocio(f"pregunta {p.orden}: selección inválida")
        return sorted(set(valor), key=p.opciones.index)  # sin duplicados, en orden original
    if p.tipo == TipoPregunta.ESCALA:
        if not isinstance(valor, int) or isinstance(valor, bool) or not ESCALA_MIN <= valor <= ESCALA_MAX:
            raise ErrorNegocio(f"pregunta {p.orden}: la escala va de {ESCALA_MIN} a {ESCALA_MAX}")
        return valor
    if not isinstance(valor, str) or not valor.strip() or len(valor) > 2000:
        raise ErrorNegocio(f"pregunta {p.orden}: texto inválido")
    return valor.strip()


def responder(s: Session, encuesta: Encuesta, valores: dict[str, Any], codigo: str | None,
              ahora: datetime) -> Respuesta:
    """Registra una respuesta anónima validando todas las reglas."""
    if not encuesta.abierta or (encuesta.cierra_en is not None and ahora >= encuesta.cierra_en):
        raise ErrorNegocio("la encuesta está cerrada", 409)
    por_id = {str(p.id): p for p in encuesta.preguntas}
    desconocidas = set(valores) - set(por_id)
    if desconocidas:
        raise ErrorNegocio(f"preguntas desconocidas: {sorted(desconocidas)}")
    limpio = {}
    for pid, p in por_id.items():
        if pid not in valores or valores[pid] in (None, "", []):
            if p.obligatoria:
                raise ErrorNegocio(f"pregunta {p.orden} obligatoria")
            continue
        limpio[pid] = validar_valor(p, valores[pid])
    if encuesta.requiere_codigo:
        if not codigo:
            raise ErrorNegocio("esta encuesta requiere código de invitación", 403)
        # Consumo atómico: solo una petición puede pasar el código de False a True.
        r = s.execute(update(Codigo).where(Codigo.encuesta_id == encuesta.id,
                                           Codigo.codigo_hash == hash_codigo(codigo), Codigo.usado.is_(False))
                      .values(usado=True))
        if r.rowcount != 1:
            raise ErrorNegocio("código inválido o ya utilizado", 403)
    resp = Respuesta(encuesta_id=encuesta.id, valores=limpio)
    s.add(resp)
    s.flush()
    return resp


def resultados(s: Session, encuesta: Encuesta) -> dict:
    """Agrega: conteos por opción, promedio/distribución de escala y textos."""
    respuestas = list(s.scalars(select(Respuesta.valores).where(Respuesta.encuesta_id == encuesta.id)))
    salida = {"total": len(respuestas), "preguntas": []}
    for p in encuesta.preguntas:
        valores = [r[str(p.id)] for r in respuestas if str(p.id) in r]
        item: dict[str, Any] = {"id": p.id, "orden": p.orden, "texto": p.texto, "tipo": p.tipo.value,
                                "respondidas": len(valores)}
        if p.tipo == TipoPregunta.UNICA:
            cuenta = Counter(valores)
            item["conteo"] = {o: cuenta.get(o, 0) for o in p.opciones}
        elif p.tipo == TipoPregunta.MULTIPLE:
            cuenta = Counter(v for lista in valores for v in lista)
            item["conteo"] = {o: cuenta.get(o, 0) for o in p.opciones}
        elif p.tipo == TipoPregunta.ESCALA:
            cuenta = Counter(valores)
            item["conteo"] = {str(i): cuenta.get(i, 0) for i in range(ESCALA_MIN, ESCALA_MAX + 1)}
            item["promedio"] = round(mean(valores), 2) if valores else None
        else:
            item["textos"] = valores
        salida["preguntas"].append(item)
    return salida


def exportar_csv(s: Session, encuesta: Encuesta) -> str:
    """CSV con una fila por respuesta y una columna por pregunta.

    Las celdas que empiezan con ``= + - @`` se prefijan con ``'`` para evitar
    inyección de fórmulas al abrir el archivo en una planilla.
    """
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([p.texto for p in encuesta.preguntas])
    for valores in s.scalars(select(Respuesta.valores).where(Respuesta.encuesta_id == encuesta.id).order_by(Respuesta.id)):
        fila = []
        for p in encuesta.preguntas:
            v = valores.get(str(p.id), "")
            v = "; ".join(v) if isinstance(v, list) else str(v)
            fila.append("'" + v if v[:1] in ("=", "+", "-", "@") else v)
        w.writerow(fila)
    return buf.getvalue()
