"""Resumen estadístico: promedio, distribución, sentimiento y palabras frecuentes."""
from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .modelo import Resena
from .sentimiento import _tokens, clasificar, puntuar

# Palabras vacías (artículos, preposiciones...) que no aportan al ranking de temas.
VACIAS = {"el", "la", "los", "las", "un", "una", "de", "del", "y", "a", "que", "en", "es", "lo", "me", "se",
          "por", "con", "para", "muy", "pero", "mi", "al", "no", "su", "le", "ya", "le", "the", "and", "it", "is"}


@dataclass(frozen=True)
class Resumen:
    """Estadísticas agregadas de un conjunto de reseñas."""
    cantidad: int
    promedio_estrellas: float | None
    # Estrellas (5 a 1) → cantidad de reseñas.
    distribucion: dict[int, int]
    # "positiva"/"negativa"/"neutral" → cantidad.
    sentimientos: dict[str, int]
    sentimiento_medio: float
    temas_positivos: list[str]
    temas_negativos: list[str]
    discrepancias: int   # p. ej. 5 estrellas con texto negativo (posibles errores o ironía)


def resumir(resenas: list[Resena], top: int = 5) -> Resumen:
    """Calcula el Resumen; `top` limita la cantidad de temas por polaridad."""
    puntajes = [puntuar(r.texto) for r in resenas]
    clases = [clasificar(p) for p in puntajes]
    estrellas = [r.estrellas for r in resenas if r.estrellas is not None]
    # Se redondea a estrellas enteras para el histograma.
    dist = Counter(round(e) for e in estrellas)
    pos, neg = Counter(), Counter()
    for r, c in zip(resenas, clases):
        # Palabras de más de 3 letras que no sean vacías.
        palabras = [t for t in _tokens(r.texto) if t not in VACIAS and len(t) > 3]
        # set(): cada reseña cuenta una vez por palabra; las neutrales van a un Counter descartable.
        (pos if c == "positiva" else neg if c == "negativa" else Counter()).update(set(palabras))
    # Discrepancia: 4-5 estrellas con texto negativo, o 1-2 estrellas con texto positivo.
    disc = sum(1 for r, c in zip(resenas, clases) if r.estrellas is not None and
               ((r.estrellas >= 4 and c == "negativa") or (r.estrellas <= 2 and c == "positiva")))
    # Promedios redondeados; None / 0.0 si no hay datos.
    return Resumen(len(resenas), round(sum(estrellas) / len(estrellas), 2) if estrellas else None,
                   {k: dist.get(k, 0) for k in range(5, 0, -1)}, dict(Counter(clases)),
                   round(sum(puntajes) / len(puntajes), 3) if puntajes else 0.0,
                   [w for w, _ in pos.most_common(top)], [w for w, _ in neg.most_common(top)], disc)


def exportar_csv(resenas: list[Resena], ruta: Path) -> Path:
    """Escribe una fila por reseña, con su sentimiento calculado, y devuelve la ruta."""
    with Path(ruta).open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["autor", "estrellas", "titulo", "fecha", "verificada", "sentimiento", "puntaje", "texto"])
        for r in resenas:
            p = puntuar(r.texto)
            w.writerow([r.autor, r.estrellas, r.titulo, r.fecha, r.verificada, clasificar(p), p, r.texto])
    return Path(ruta)
