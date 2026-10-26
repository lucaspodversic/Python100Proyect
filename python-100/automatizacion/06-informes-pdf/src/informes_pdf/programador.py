"""Programación de ejecuciones (diaria o semanal) sin dependencias externas.

En producción se recomienda cron / Programador de tareas de Windows llamando
a la CLI; este módulo permite además un modo "demonio" simple y testeable.
"""

from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Programacion:
    """``hora``/``minuto`` de ejecución; ``dia_semana`` 0=lunes (``None`` = diario)."""

    hora: int
    minuto: int = 0
    dia_semana: int | None = None


def proxima_ejecucion(prog: Programacion, ahora: dt.datetime) -> dt.datetime:
    """Calcula el próximo instante (estrictamente futuro) que cumple la programación."""
    # Candidato = hoy a la hora programada. Si ya pasó (o es exactamente ahora), se va al día
    # siguiente: "estrictamente futuro" evita ejecutar dos veces en el mismo minuto.
    candidato = ahora.replace(hour=prog.hora, minute=prog.minuto, second=0, microsecond=0)
    if prog.dia_semana is None:
        return candidato if candidato > ahora else candidato + dt.timedelta(days=1)
    # Días hasta el próximo día de semana pedido; el módulo 7 da 0 si es hoy.
    dias = (prog.dia_semana - ahora.weekday()) % 7
    candidato += dt.timedelta(days=dias)
    # Si es hoy pero la hora ya pasó, la próxima es dentro de una semana.
    return candidato if candidato > ahora else candidato + dt.timedelta(days=7)


def ejecutar_programado(
    prog: Programacion,
    tarea: Callable[[], object],
    veces: int | None = None,
    reloj: Callable[[], dt.datetime] = dt.datetime.now,
    dormir: Callable[[float], None] = time.sleep,
) -> int:
    """Duerme hasta cada próxima ejecución y corre ``tarea``. Devuelve las ejecuciones."""
    hechas = 0
    # Se recalcula la espera en cada vuelta (no se suman 24 h fijas): así se corrige la deriva
    # si la tarea tarda o si el reloj del sistema cambió.
    while veces is None or hechas < veces:
        ahora = reloj()
        dormir((proxima_ejecucion(prog, ahora) - ahora).total_seconds())
        tarea()
        hechas += 1
    return hechas
