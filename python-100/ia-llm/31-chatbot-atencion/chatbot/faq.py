"""Base de preguntas frecuentes y búsqueda por similitud léxica.

Se usa un puntaje sencillo y explicable: solapamiento de tokens normalizados
(sin tildes, sin palabras vacías) ponderado por IDF, para recuperar las FAQ más
relevantes y pasárselas al LLM como contexto (mini-RAG sin embeddings).
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

PALABRAS_VACIAS = set("""a al algo como con de del el en es esta este hay la las lo los me mi mis no o para
pero por que qué se si sin su sus te tu un una y ya yo puedo quiero tengo hacer hago""".split())


def normalizar(texto: str) -> list[str]:
    """Minúsculas, sin tildes, solo palabras de 2+ letras que no sean vacías.
    Además aplica un 'stemming' mínimo: quita la 's' final de plurales."""
    t = unicodedata.normalize("NFKD", texto.lower())
    # NFKD separa letra y tilde; se descartan las marcas combinantes.
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    tokens = re.findall(r"[a-z0-9]{2,}", t)
    # "envios" -> "envio", pero palabras cortas como "mes" o "gas" no se tocan.
    return [tk[:-1] if len(tk) > 4 and tk.endswith("s") else tk
            for tk in tokens if tk not in PALABRAS_VACIAS]


@dataclass(frozen=True)
class EntradaFAQ:
    pregunta: str
    respuesta: str
    categoria: str = "general"


class BaseFAQ:
    """Colección de FAQ con índice IDF precalculado."""

    def __init__(self, entradas: list[EntradaFAQ]) -> None:
        self.entradas = entradas
        # Se indexan pregunta y categoría (la categoría suma palabras clave).
        self._tokens = [set(normalizar(e.pregunta + " " + e.categoria)) for e in entradas]
        n = len(entradas)
        df: dict[str, int] = {}
        for ts in self._tokens:
            for t in ts:
                df[t] = df.get(t, 0) + 1
        # IDF suavizado: términos raros pesan más
        # Ej.: con 10 FAQ, una palabra en 1 => log(11) ≈ 2,40; en las 10 => log(2) ≈ 0,69.
        self._idf = {t: math.log(1 + n / c) for t, c in df.items()}

    @classmethod
    def desde_json(cls, ruta: str | Path) -> "BaseFAQ":
        datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
        return cls([EntradaFAQ(**d) for d in datos])

    def buscar(self, consulta: str, k: int = 3, umbral: float = 0.3) -> list[tuple[EntradaFAQ, float]]:
        """Devuelve hasta k FAQ con puntaje normalizado (0..1) >= umbral."""
        q = set(normalizar(consulta))
        if not q:
            return []
        resultados = []
        for entrada, ts in zip(self.entradas, self._tokens):
            comunes = q & ts
            if not comunes:
                continue
            # Parte 1: qué fracción del "peso" de la FAQ cubre la consulta.
            total = sum(self._idf.get(t, 0) for t in ts) or 1
            puntaje = sum(self._idf[t] for t in comunes) / total
            # Bonus por cobertura de la consulta (cuántas palabras del usuario aparecen)
            puntaje = 0.5 * puntaje + 0.5 * len(comunes) / len(q)
            # Umbral 0,3: por debajo se considera ruido y se prefiere decir "no sé".
            if puntaje >= umbral:
                resultados.append((entrada, round(puntaje, 3)))
        resultados.sort(key=lambda x: -x[1])
        return resultados[:k]
