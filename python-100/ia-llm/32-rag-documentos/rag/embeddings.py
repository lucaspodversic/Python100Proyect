"""Embeddings locales (sin red) e índice vectorial con similitud coseno.

`Embedder` es una interfaz: aquí se implementa TF-IDF en Python puro, pero
podría enchufarse un modelo real (sentence-transformers, API de embeddings)
sin cambiar el resto del pipeline.

Los vectores son *dispersos* (dict término -> peso) porque TF-IDF tiene
miles de dimensiones casi todas en cero.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Protocol

from rag.documentos import Fragmento

Vector = dict[str, float]
VACIAS = set("a al como con de del el en es la las lo los o para por que se su un una y".split())


def tokenizar(texto: str) -> list[str]:
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return [w for w in re.findall(r"[a-z0-9]{2,}", t) if w not in VACIAS]


def coseno(a: Vector, b: Vector) -> float:
    """Similitud coseno entre vectores dispersos (0 = nada en común, 1 = igual)."""
    # Se itera el vector más chico (el producto solo suma claves comunes).
    if len(a) > len(b):
        a, b = b, a
    producto = sum(v * b.get(k, 0.0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    # Un vector vacío (consulta sin palabras conocidas) => similitud 0.
    return producto / (na * nb) if na and nb else 0.0


class Embedder(Protocol):
    def ajustar(self, textos: list[str]) -> None: ...
    def vectorizar(self, texto: str) -> Vector: ...


class EmbedderTFIDF:
    """TF-IDF con TF sublineal (1 + log tf) e IDF suavizado."""

    def __init__(self) -> None:
        self.idf: dict[str, float] = {}

    def ajustar(self, textos: list[str]) -> None:
        n = len(textos)
        df = Counter(t for tx in textos for t in set(tokenizar(tx)))
        # IDF suavizado (como scikit-learn): el +1 evita que una palabra presente
        # en todos los documentos pese 0. Ej.: 2 docs, df=1 => ln(3/2)+1 ≈ 1,41;
        # df=2 => ln(3/3)+1 = 1.
        self.idf = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items()}

    def vectorizar(self, texto: str) -> Vector:
        # TF sublineal: una palabra repetida 10 veces no pesa 10 veces más (1 + ln 10 ≈ 3,3).
        tf = Counter(tokenizar(texto))
        # términos fuera del vocabulario se ignoran (no aportan a la similitud)
        return {t: (1 + math.log(c)) * self.idf[t] for t, c in tf.items() if t in self.idf}


class IndiceVectorial:
    """Índice en memoria con búsqueda exacta (fuerza bruta) y persistencia JSON."""

    def __init__(self, embedder: Embedder | None = None) -> None:
        self.embedder = embedder or EmbedderTFIDF()
        self.fragmentos: list[Fragmento] = []
        self.vectores: list[Vector] = []

    def indexar(self, fragmentos: list[Fragmento]) -> None:
        self.fragmentos = list(fragmentos)
        self.embedder.ajustar([f.texto for f in self.fragmentos])
        self.vectores = [self.embedder.vectorizar(f.texto) for f in self.fragmentos]

    def buscar(self, consulta: str, k: int = 4, minimo: float = 0.05) -> list[tuple[Fragmento, float]]:
        q = self.embedder.vectorizar(consulta)
        # Búsqueda exacta O(n): para miles de fragmentos alcanza; con millones se
        # usaría un índice aproximado (FAISS, HNSW).
        puntajes = [(f, coseno(q, v)) for f, v in zip(self.fragmentos, self.vectores)]
        puntajes = [(f, round(s, 4)) for f, s in puntajes if s >= minimo]
        return sorted(puntajes, key=lambda x: -x[1])[:k]

    # --- persistencia (solo para el embedder TF-IDF) ---
    def guardar(self, ruta: str | Path) -> None:
        # Solo se persiste el IDF y los textos; los vectores se recalculan al cargar
        # (son deterministas a partir de esos dos datos).
        assert isinstance(self.embedder, EmbedderTFIDF)
        datos = {"idf": self.embedder.idf, "fragmentos": [f.__dict__ for f in self.fragmentos]}
        Path(ruta).write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def cargar(cls, ruta: str | Path) -> "IndiceVectorial":
        datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
        emb = EmbedderTFIDF(); emb.idf = datos["idf"]
        ind = cls(emb)
        ind.fragmentos = [Fragmento(**f) for f in datos["fragmentos"]]
        ind.vectores = [emb.vectorizar(f.texto) for f in ind.fragmentos]
        return ind
