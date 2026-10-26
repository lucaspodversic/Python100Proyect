"""Algoritmo Apriori y generación de reglas, sin librerías externas.

Idea clave (propiedad *anti-monótona*): si un conjunto es infrecuente, todos
sus superconjuntos también lo son. Por eso:

1. Se cuentan los ítems sueltos (L1) y se descartan los infrecuentes.
2. Candidatos de tamaño k = uniones de conjuntos frecuentes de tamaño k-1
   que comparten k-2 ítems (*join*), descartando los que tengan algún
   subconjunto infrecuente (*prune*).
3. Se cuentan los candidatos en una pasada sobre los tickets. Se repite
   hasta que no queden candidatos.

Métricas de una regla A → B:
- soporte(A∪B)     = P(A y B)
- confianza        = P(B | A) = sop(A∪B) / sop(A)
- lift             = confianza / sop(B)   (> 1: se compran juntos más que por azar)
- leverage         = sop(A∪B) − sop(A)·sop(B)
- conviction       = (1 − sop(B)) / (1 − confianza)   (∞ si la regla nunca falla)
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from typing import Iterable

# frozenset: inmutable y hasheable, sirve como clave de dict y no depende del orden de los ítems.
Conjunto = frozenset[str]


def apriori(tickets: Iterable[Iterable[str]], soporte_min: float = 0.02,
            max_tamano: int | None = None) -> dict[Conjunto, float]:
    """Devuelve ``{conjunto_frecuente: soporte}``."""
    # soporte 0 haría "frecuentes" a todas las combinaciones posibles (explosión combinatoria).
    if not 0 < soporte_min <= 1:
        raise ValueError("soporte_min debe estar en (0, 1]")
    canastas = [frozenset(t) for t in tickets]
    # Tickets vacíos se descartan: no aportan conjuntos y distorsionarían el denominador n.
    canastas = [c for c in canastas if c]
    n = len(canastas)
    if n == 0:
        return {}
    # Se compara contra conteos enteros (sin dividir en cada paso); la división se hace al guardar.
    minimo = soporte_min * n  # en cantidad de tickets

    # Paso 1: soporte de cada ítem suelto (L1).
    conteo = Counter(item for c in canastas for item in c)
    actuales = {frozenset([i]): v for i, v in conteo.items() if v >= minimo}
    frecuentes: dict[Conjunto, float] = {k: v / n for k, v in actuales.items()}
    k = 2
    # Se termina cuando un nivel no deja conjuntos frecuentes o se alcanza el tamaño máximo pedido.
    while actuales and (max_tamano is None or k <= max_tamano):
        candidatos = _generar_candidatos(set(actuales), k)
        if not candidatos:
            break
        cuenta: Counter[Conjunto] = Counter()
        for c in canastas:
            # Un ticket con menos de k ítems no puede contener ningún candidato de tamaño k.
            if len(c) < k:
                continue
            # Recorremos lo más barato: los candidatos o las combinaciones del ticket.
            if len(candidatos) < _comb(len(c), k):
                # `<=` entre frozensets = "es subconjunto de".
                cuenta.update(cand for cand in candidatos if cand <= c)
            else:
                cuenta.update(s for s in map(frozenset, combinations(sorted(c), k)) if s in candidatos)
        actuales = {s: v for s, v in cuenta.items() if v >= minimo}
        frecuentes.update({s: v / n for s, v in actuales.items()})
        k += 1
    return frecuentes


def _comb(n: int, k: int) -> int:
    # comb(n, k) = combinaciones de n en k (número de subconjuntos de tamaño k de un ticket).
    from math import comb
    return comb(n, k)


def _generar_candidatos(previos: set[Conjunto], k: int) -> set[Conjunto]:
    """*Join* + *prune* de Apriori."""
    # Tuplas ordenadas para el join: dos conjuntos se unen sólo si comparten los primeros k-2 ítems.
    ordenados = sorted(tuple(sorted(s)) for s in previos)
    candidatos: set[Conjunto] = set()
    for i, a in enumerate(ordenados):
        for b in ordenados[i + 1:]:
            if a[:-1] != b[:-1]:
                break  # al estar ordenados, ya no habrá más con el mismo prefijo
            # Prune: el candidato sobrevive sólo si todos sus subconjuntos de tamaño k-1 son frecuentes.
            cand = frozenset(a) | frozenset(b)
            if all(frozenset(sub) in previos for sub in combinations(sorted(cand), k - 1)):
                candidatos.add(cand)
    return candidatos


# Regla inmutable: es un resultado, no debería modificarse después de calculada.
@dataclass(frozen=True)
class Regla:
    antecedente: Conjunto
    consecuente: Conjunto
    soporte: float
    confianza: float
    lift: float
    leverage: float
    conviction: float

    def __str__(self) -> str:
        a, b = ", ".join(sorted(self.antecedente)), ", ".join(sorted(self.consecuente))
        # En f-strings "{{" y "}}" son llaves literales: muestra {a} → {b}.
        return f"{{{a}}} → {{{b}}}  sop={self.soporte:.3f} conf={self.confianza:.2f} lift={self.lift:.2f}"


def generar_reglas(frecuentes: dict[Conjunto, float], confianza_min: float = 0.5,
                   lift_min: float = 1.0) -> list[Regla]:
    """Todas las reglas A → B con A∪B frecuente, ordenadas por lift y confianza."""
    reglas: list[Regla] = []
    for conjunto, sop in frecuentes.items():
        if len(conjunto) < 2:
            continue
        # Todas las particiones (antecedente, consecuente) no vacías del conjunto frecuente.
        for r in range(1, len(conjunto)):
            for ant in map(frozenset, combinations(sorted(conjunto), r)):
                cons = conjunto - ant
                conf = sop / frecuentes[ant]  # ant es frecuente por anti-monotonía
                sop_b = frecuentes[cons]
                lift = conf / sop_b
                if conf < confianza_min or lift < lift_min:
                    continue
                # Confianza 1 (la regla nunca falla) daría división por cero: conviction = ∞ por definición.
                conviction = float("inf") if conf >= 1 else (1 - sop_b) / (1 - conf)
                reglas.append(Regla(ant, cons, sop, conf, lift, sop - frecuentes[ant] * sop_b, conviction))
    # Desempate final alfabético por antecedente: orden determinista entre corridas.
    return sorted(reglas, key=lambda x: (-x.lift, -x.confianza, sorted(x.antecedente)))
