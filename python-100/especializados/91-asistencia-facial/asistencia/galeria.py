"""Registro de personas (con consentimiento) e identificación por distancia.

Decisiones de diseño:

* **Consentimiento obligatorio.** No se puede registrar a nadie sin
  :class:`Consentimiento` (quién, cuándo y finalidad). Los datos biométricos
  son una categoría especial en el RGPD (art. 9) y en muchas leyes locales.
* **Solo se guardan embeddings**, nunca fotos. Cada persona tiene un centroide
  normalizado calculado a partir de varias muestras.
* **Derecho al olvido**: :meth:`Galeria.olvidar` borra los vectores.
* **Decisión prudente**: para aceptar una identidad, la distancia debe quedar
  bajo el umbral **y** haber margen respecto a la segunda candidata. Ante la
  duda, la respuesta es "desconocido": es preferible pedir un fichaje manual a
  marcar a la persona equivocada.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from .pipeline import normalizar

UMBRAL = 0.6      # distancia euclídea típica de face_recognition (sobre vectores unitarios es más estricta)
MARGEN = 0.1      # diferencia mínima con la segunda mejor candidata
MIN_MUESTRAS = 3


@dataclass(frozen=True)
class Consentimiento:
    """Constancia del consentimiento: quién lo otorgó, cuándo y para qué finalidad. Sin esto no
    se registra a nadie (los datos biométricos son datos sensibles en la mayoría de las
    leyes de protección de datos).
    """
    otorgado_por: str
    fecha: str          # ISO 8601
    finalidad: str = "control de asistencia"


@dataclass(frozen=True)
class Resultado:
    """Resultado de identificar una cara: persona (o None), distancia al mejor centroide y
    motivo del rechazo, si lo hubo.
    """
    persona: str | None   # None = desconocido
    distancia: float
    motivo: str = ""


class Galeria:
    """Galería de personas registradas. Guarda SOLO un centroide (vector promedio de 128
    números) por persona, nunca fotos, más su consentimiento. Identifica por distancia
    euclídea con un umbral y exige un margen respecto de la segunda candidata para no
    confundir personas parecidas.
    """
    def __init__(self, umbral: float = UMBRAL, margen: float = MARGEN) -> None:
        """``umbral``: distancia máxima para aceptar. ``margen``: ventaja mínima sobre la
        segunda candidata.
        """
        self.umbral = umbral
        self.margen = margen
        self._centroides: dict[str, np.ndarray] = {}
        self._consentimientos: dict[str, Consentimiento] = {}

    def __contains__(self, persona: str) -> bool:
        """Permite ``'ana' in galeria``."""
        return persona in self._centroides

    def personas(self) -> list[str]:
        """Personas registradas en orden alfabético."""
        return sorted(self._centroides)

    def registrar(self, persona: str, muestras: list[np.ndarray], consentimiento: Consentimiento | None) -> None:
        """Registra a una persona a partir de al menos MIN_MUESTRAS embeddings. Exige un
        consentimiento con firmante no vacío y rechaza muestras dispersas (más lejos
        que el umbral del promedio), que suelen ser fotos de personas distintas o de
        mala calidad.
        """
        if consentimiento is None or not consentimiento.otorgado_por.strip():
            raise PermissionError("no se puede registrar sin consentimiento explícito")
        if len(muestras) < MIN_MUESTRAS:
            raise ValueError(f"se necesitan al menos {MIN_MUESTRAS} muestras")
        m = np.stack([normalizar(np.asarray(v, dtype=float)) for v in muestras])
        # Muestras muy dispersas suelen indicar fotos de personas distintas o de mala calidad.
        centro = normalizar(m.mean(axis=0))
        if float(np.max(np.linalg.norm(m - centro, axis=1))) > self.umbral:
            raise ValueError("muestras inconsistentes: ¿son todas de la misma persona?")
        self._centroides[persona] = centro
        self._consentimientos[persona] = consentimiento

    def olvidar(self, persona: str) -> bool:
        """Elimina toda la información biométrica de la persona."""
        self._consentimientos.pop(persona, None)
        return self._centroides.pop(persona, None) is not None

    def identificar(self, embedding: np.ndarray) -> Resultado:
        """Compara contra todos los centroides. Devuelve desconocido si la galería está vacía,
        si la mejor distancia supera el umbral o si la segunda candidata está a
        menos de ``margen`` (ambiguo). Es preferible no fichar que fichar a la
        persona equivocada.
        """
        if not self._centroides:
            return Resultado(None, float("inf"), "galería vacía")
        v = normalizar(np.asarray(embedding, dtype=float))
        dist = sorted((float(np.linalg.norm(c - v)), p) for p, c in self._centroides.items())
        d1, mejor = dist[0]
        if d1 > self.umbral:
            return Resultado(None, d1, "sin coincidencia")
        if len(dist) > 1 and dist[1][0] - d1 < self.margen:
            return Resultado(None, d1, "ambiguo")
        return Resultado(mejor, d1)

    # --- Persistencia (JSON; en producción convendría cifrarlo en reposo) ---
    def guardar(self, ruta: Path) -> None:
        """Persiste centroides (redondeados a 6 decimales) y consentimientos en JSON. No guarda
        imágenes.
        """
        datos = {p: {"centroide": c.round(6).tolist(), "consentimiento": asdict(self._consentimientos[p])}
                 for p, c in self._centroides.items()}
        ruta.write_text(json.dumps(datos), encoding="utf-8")

    @classmethod
    def cargar(cls, ruta: Path, **kw) -> "Galeria":
        """Reconstruye la galería desde JSON, renormalizando los vectores (el redondeo los
        aleja apenas de norma 1).
        """
        g = cls(**kw)
        for p, d in json.loads(ruta.read_text(encoding="utf-8")).items():
            g._centroides[p] = normalizar(np.asarray(d["centroide"]))
            g._consentimientos[p] = Consentimiento(**d["consentimiento"])
        return g


def consentimiento_ahora(persona: str, finalidad: str = "control de asistencia") -> Consentimiento:
    """Atajo para crear un consentimiento con la fecha actual."""
    return Consentimiento(persona, datetime.now().isoformat(timespec="seconds"), finalidad)
