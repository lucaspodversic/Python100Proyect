"""Máquina de estados de una entrevista.

    INICIO --iniciar()--> PREGUNTANDO --responder()--> (REPREGUNTA | PREGUNTANDO | FINALIZADA)
                                  REPREGUNTA --responder()--> PREGUNTANDO | FINALIZADA

Una repregunta (seguimiento) se hace como máximo una vez por pregunta, y solo
si el puntaje fue intermedio (ni excelente ni muy malo): ahí es donde más
información aporta.
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from entrevistas.banco import Pregunta
from entrevistas.evaluador import Evaluacion, evaluar
from entrevistas.llm import ProveedorLLM


# Heredar de str permite serializar el estado directo a JSON.
class Estado(str, Enum):
    INICIO = "inicio"
    PREGUNTANDO = "preguntando"
    REPREGUNTA = "repregunta"
    FINALIZADA = "finalizada"


@dataclass
class Turno:
    pregunta: Pregunta
    texto_pregunta: str
    respuesta: str
    evaluacion: Evaluacion
    segundos: float
    es_repregunta: bool = False


@dataclass
class Sesion:
    preguntas: list[Pregunta]
    llm: ProveedorLLM
    # Reloj inyectable para medir el tiempo de respuesta de forma testeable.
    reloj: Callable[[], float] = time.monotonic
    repreguntar: bool = True
    estado: Estado = Estado.INICIO
    turnos: list[Turno] = field(default_factory=list)
    # Estado interno: índice de la pregunta actual, repregunta pendiente e
    # instante en que se mostró la pregunta.
    _indice: int = 0
    _repregunta: str | None = None
    _t0: float = 0.0

    def iniciar(self) -> str:
        if self.estado is not Estado.INICIO:
            raise RuntimeError("La sesión ya empezó")
        self.estado = Estado.PREGUNTANDO
        return self.pregunta_actual()

    def pregunta_actual(self) -> str:
        if self.estado is Estado.FINALIZADA:
            raise RuntimeError("La entrevista terminó")
        # El cronómetro arranca cuando se muestra la pregunta.
        self._t0 = self.reloj()
        return self._repregunta if self.estado is Estado.REPREGUNTA else self.preguntas[self._indice].texto

    def responder(self, respuesta: str) -> tuple[Evaluacion, str | None]:
        """Evalúa la respuesta y devuelve (evaluación, siguiente pregunta o None si terminó)."""
        # Responder antes de iniciar o después de terminar es un error de uso.
        if self.estado not in (Estado.PREGUNTANDO, Estado.REPREGUNTA):
            raise RuntimeError(f"No se puede responder en estado {self.estado.value}")
        p = self.preguntas[self._indice]
        es_rep = self.estado is Estado.REPREGUNTA
        texto = self._repregunta if es_rep else p.texto
        ev = evaluar(p, respuesta, self.llm)
        self.turnos.append(Turno(p, texto or "", respuesta, ev, round(self.reloj() - self._t0, 1), es_rep))
        # Repregunta solo si: no es ya una repregunta (máximo una), está activada,
        # el evaluador propuso una y el puntaje es intermedio (4 a 7).
        if not es_rep and self.repreguntar and ev.repregunta and 4 <= ev.puntaje <= 7:
            self.estado, self._repregunta = Estado.REPREGUNTA, ev.repregunta
        else:
            self._indice += 1
            self._repregunta = None
            self.estado = Estado.FINALIZADA if self._indice >= len(self.preguntas) else Estado.PREGUNTANDO
        return ev, (None if self.estado is Estado.FINALIZADA else self.pregunta_actual())

    def informe(self) -> dict:
        """Puntaje global y por competencia, más las mejoras más frecuentes."""
        if self.estado is not Estado.FINALIZADA:
            raise RuntimeError("La entrevista no terminó")
        por_comp: dict[str, list[int]] = defaultdict(list)
        for t in self.turnos:
            por_comp[t.pregunta.competencia].append(t.evaluacion.puntaje)
        # Las repreguntas cuentan como turnos: pesan igual que una pregunta.
        promedio = sum(t.evaluacion.puntaje for t in self.turnos) / len(self.turnos)
        mejoras = [m for t in self.turnos for m in t.evaluacion.mejoras]
        return {"puntaje_global": round(promedio, 1),
                # Umbrales: >= 7 avanza, 5 a 6,9 a revisar, < 5 no avanza.
                "veredicto": "avanza" if promedio >= 7 else "a revisar" if promedio >= 5 else "no avanza",
                "por_competencia": {c: round(sum(v) / len(v), 1) for c, v in por_comp.items()},
                "tiempo_total_s": round(sum(t.segundos for t in self.turnos), 1),
                "mejoras": mejoras[:5]}
