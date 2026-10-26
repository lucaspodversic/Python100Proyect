"""Algoritmos de ordenamiento de hilos.

- "nuevos": por fecha descendente.
- "top": por puntaje (votos positivos - negativos).
- "populares" (hot): fórmula al estilo Reddit, donde el puntaje pesa de forma
  logarítmica y la antigüedad penaliza linealmente. Así un hilo nuevo con pocos
  votos puede superar a uno viejo con muchos.
"""
from __future__ import annotations

import math

# Época de referencia (segundos) y "vida media" del ranking: 12,5 horas
# 1.700.000.000 ≈ noviembre 2023. Restarla mantiene los números chicos.
# DIVISOR = 45.000 s = 12,5 h: cada 12,5 h de "juventud" vale lo mismo que
# multiplicar los votos por 10 (una unidad de log10).
EPOCA = 1_700_000_000
DIVISOR = 45_000


def puntaje_hot(puntaje: int, creado_ts: float) -> float:
    """Calcula el valor 'hot': log10 del puntaje con signo + bonificación por recencia."""
    # log10: los primeros 10 votos pesan lo mismo que los siguientes 90.
    # max(..., 1) evita log10(0); un hilo con 0 o ±1 voto tiene orden 0.
    orden = math.log10(max(abs(puntaje), 1))
    # El signo hace que un hilo con votos negativos baje en vez de subir.
    signo = 1 if puntaje > 0 else -1 if puntaje < 0 else 0
    # El término de tiempo crece con la fecha de creación: más nuevo => más alto.
    # Se redondea para que la salida JSON sea estable.
    return round(signo * orden + (creado_ts - EPOCA) / DIVISOR, 7)
