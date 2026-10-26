"""Pipeline de visión detrás de una interfaz.

Un :class:`Extractor` recibe una imagen y devuelve las caras encontradas, cada
una con su *embedding*: un vector que resume la cara, de modo que dos fotos de
la misma persona quedan cerca.

* :class:`ExtractorFaceRecognition` usa la librería ``face_recognition``
  (dlib, vectores de 128 dimensiones) y OpenCV. Es opcional (``pip install
  .[vision]``).
* :class:`ExtractorSintetico` no hace visión: la "imagen" es una lista de
  identidades y genera embeddings deterministas con ruido controlado. Permite
  probar todo el sistema sin cámara, sin modelos y **sin datos biométricos
  reales**.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

DIM = 128  # dimensión de los embeddings de face_recognition


@dataclass(frozen=True)
class Cara:
    """Una cara detectada: caja en la convención de face_recognition y embedding de norma 1."""
    caja: tuple[int, int, int, int]   # (arriba, derecha, abajo, izquierda), convención de face_recognition
    embedding: np.ndarray


class Extractor(Protocol):
    """Interfaz de detección y extracción: la implementación real (face_recognition) o la
    sintética de los tests.
    """
    def extraer(self, imagen: Any) -> list[Cara]:
        """Detecta las caras de ``imagen`` y devuelve su caja y embedding normalizado."""
        ...


def normalizar(v: np.ndarray) -> np.ndarray:
    """Lleva el vector a norma 1 (el vector cero queda igual, para no dividir por cero)."""
    n = float(np.linalg.norm(v))
    return v / n if n else v


class ExtractorFaceRecognition:
    """Detección HOG (CPU) o CNN y embeddings de 128 dimensiones con dlib."""

    def __init__(self, modelo: str = "hog") -> None:
        """Importa face_recognition recién acá porque es pesado y opcional. 'hog' es rápido en
        CPU; 'cnn' es más preciso pero necesita GPU.
        """
        import face_recognition  # import perezoso: dependencia pesada y opcional
        self._fr = face_recognition
        self.modelo = modelo

    def extraer(self, imagen: Any) -> list[Cara]:
        """Detecta las caras y calcula un embedding de 128 dimensiones para cada una."""
        # face_recognition espera RGB; OpenCV entrega BGR → invertir canales.
        rgb = np.ascontiguousarray(imagen[:, :, ::-1])
        cajas = self._fr.face_locations(rgb, model=self.modelo)
        vecs = self._fr.face_encodings(rgb, cajas)
        return [Cara(tuple(c), normalizar(np.asarray(v))) for c, v in zip(cajas, vecs)]


def embedding_base(identidad: str, dim: int = DIM) -> np.ndarray:
    """Vector unitario pseudoaleatorio pero fijo para una identidad (semilla = sha256 del nombre)."""
    semilla = int.from_bytes(hashlib.sha256(identidad.encode()).digest()[:8], "big")
    return normalizar(np.random.default_rng(semilla).normal(size=dim))


class ExtractorSintetico:
    """La imagen es ``list[str]`` (identidades presentes). Ruido gaussiano con semilla fija."""

    def __init__(self, ruido: float = 0.03, semilla: int = 0, dim: int = DIM) -> None:
        """Extractor falso para tests: la 'imagen' es una lista de identidades. ``ruido``
        simula la variación entre fotos de la misma persona y la semilla lo hace
        reproducible.
        """
        self.ruido = ruido
        self.dim = dim
        self._rng = np.random.default_rng(semilla)

    def extraer(self, imagen: list[str]) -> list[Cara]:
        """Para cada identidad: vector base determinista (derivado del nombre) más ruido
        gaussiano, normalizado. Las cajas se ubican una al lado de la otra.
        """
        caras = []
        for i, ident in enumerate(imagen):
            v = embedding_base(ident, self.dim) + self._rng.normal(scale=self.ruido, size=self.dim)
            caras.append(Cara((0, 100 * (i + 1), 100, 100 * i), normalizar(v)))
        return caras
