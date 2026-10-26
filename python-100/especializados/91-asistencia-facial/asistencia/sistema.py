"""Orquestador: imagen → caras → identificación → confirmación → fichaje.

Para reducir falsos positivos, una persona debe reconocerse en
``confirmaciones`` fotogramas **consecutivos** antes de fichar. Un único
fotograma borroso no basta.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .galeria import Galeria
from .pipeline import Extractor
from .registro import Fichaje, Registro


@dataclass
class Sistema:
    """Une extractor, galería y registro. Para fichar exige que la persona aparezca en
    ``confirmaciones`` fotogramas SEGUIDOS: un falso positivo aislado no genera un
    fichaje. Cuenta los desconocidos pero no guarda nada de ellos.
    """
    extractor: Extractor
    galeria: Galeria
    registro: Registro
    confirmaciones: int = 3
    reloj: Callable[[], datetime] = datetime.now
    _racha: dict[str, int] = field(default_factory=dict)
    desconocidos: int = 0

    def procesar(self, imagen: Any) -> list[Fichaje]:
        """Procesa un fotograma y devuelve los fichajes nuevos. Una persona ficha exactamente
        cuando su racha llega a ``confirmaciones`` (no en cada fotograma siguiente)
        y la racha se reinicia si sale de cuadro.
        """
        vistos: set[str] = set()
        eventos: list[Fichaje] = []
        for cara in self.extractor.extraer(imagen):
            r = self.galeria.identificar(cara.embedding)
            if r.persona is None:
                self.desconocidos += 1
                continue
            vistos.add(r.persona)
        # Las rachas de quienes no aparecen en este fotograma se reinician.
        self._racha = {p: self._racha.get(p, 0) + 1 for p in vistos}
        for p in sorted(vistos):
            if self._racha[p] == self.confirmaciones:
                f = self.registro.marcar(p, self.reloj())
                if f:
                    eventos.append(f)
        return eventos

    def olvidar(self, persona: str) -> None:
        """Derecho de supresión: biometría y fichajes."""
        self.galeria.olvidar(persona)
        self.registro.olvidar(persona)
        self._racha.pop(persona, None)
