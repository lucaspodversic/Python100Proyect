"""Evaluación de umbrales con histéresis y enfriamiento.

- Se alerta cuando una métrica supera su umbral durante N lecturas
  consecutivas (evita falsos positivos por picos breves).
- Tras alertar, no se repite la alerta de esa métrica hasta pasar el
  período de enfriamiento (evita spam en el canal).
- Cuando la métrica vuelve a la normalidad se emite una "recuperación".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .metricas import Metricas


@dataclass(frozen=True)
class Umbrales:
    """Límites por métrica (en %) y parámetros anti-ruido."""
    cpu: float = 90.0
    memoria: float = 90.0
    disco: float = 85.0
    lecturas_consecutivas: int = 3
    # 15 minutos sin repetir la misma alerta mientras siga alta.
    enfriamiento_seg: float = 900.0


@dataclass(frozen=True)
class Alerta:
    """Una alerta (o recuperación) lista para convertirse en mensaje."""
    metrica: str
    valor: float
    umbral: float
    recuperada: bool = False

    def texto(self, host: str) -> str:
        """Mensaje legible con emoji, host, valor y umbral."""
        if self.recuperada:
            return f"✅ [{host}] {self.metrica} normalizada: {self.valor:.1f}% (umbral {self.umbral:.0f}%)"
        return f"🚨 [{host}] {self.metrica} al {self.valor:.1f}% (umbral {self.umbral:.0f}%)"


@dataclass
class EvaluadorAlertas:
    """Máquina de estados por métrica: rachas, último aviso y si está en alerta."""
    umbrales: Umbrales = field(default_factory=Umbrales)
    # Reloj monotónico (no salta con cambios de hora); inyectable para tests deterministas.
    reloj: Callable[[], float] = __import__("time").monotonic
    # Estado interno: lecturas seguidas sobre el umbral, momento del último aviso y métricas en alerta.
    _rachas: dict[str, int] = field(default_factory=dict)
    _ultima_alerta: dict[str, float] = field(default_factory=dict)
    _en_alerta: set[str] = field(default_factory=set)

    def evaluar(self, m: Metricas) -> list[Alerta]:
        """Procesa una lectura y devuelve las alertas a enviar ahora."""
        salida: list[Alerta] = []
        ahora = self.reloj()
        # El mismo nombre sirve para leer el valor y su umbral (getattr sobre ambos dataclasses).
        for nombre in ("cpu", "memoria", "disco"):
            valor, umbral = getattr(m, nombre), getattr(self.umbrales, nombre)
            # Igualar el umbral ya cuenta como superarlo.
            if valor >= umbral:
                self._rachas[nombre] = self._rachas.get(nombre, 0) + 1
                ultima = self._ultima_alerta.get(nombre)
                # Primera alerta de la métrica, o pasó el enfriamiento desde la anterior.
                enfriado = ultima is None or ahora - ultima >= self.umbrales.enfriamiento_seg
                if self._rachas[nombre] >= self.umbrales.lecturas_consecutivas and enfriado:
                    # Se alerta y se anota el momento para empezar el enfriamiento.
                    salida.append(Alerta(nombre, valor, umbral))
                    self._ultima_alerta[nombre] = ahora
                    self._en_alerta.add(nombre)
            else:
                # Una lectura normal corta la racha: los picos breves nunca alertan.
                self._rachas[nombre] = 0
                # Sólo se avisa la recuperación si antes se había alertado; se reinicia el enfriamiento.
                if nombre in self._en_alerta:
                    self._en_alerta.discard(nombre)
                    self._ultima_alerta.pop(nombre, None)
                    salida.append(Alerta(nombre, valor, umbral, recuperada=True))
        return salida
