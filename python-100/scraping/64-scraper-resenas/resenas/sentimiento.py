"""Análisis de sentimiento por léxico (español + inglés básico), sin dependencias.

Algoritmo:
- Cada palabra del léxico suma (+) o resta (-).
- Un negador ("no", "nunca", "ni"...) en las 3 palabras previas invierte el signo.
- Un intensificador ("muy", "súper"...) inmediatamente antes multiplica x1.5.
- El puntaje se normaliza a [-1, 1] con x / sqrt(x² + 4) (similar a VADER).

Es deliberadamente simple y explicable; para producción conviene un modelo
entrenado (p. ej. transformers), pero esto no requiere descargar nada.
"""
from __future__ import annotations

import math
import re
import unicodedata

# Léxico sin tildes (se comparan tokens normalizados); el valor es el peso de la palabra.
POSITIVAS = {
    "bueno": 1, "buena": 1, "buenisimo": 2, "excelente": 2, "genial": 2, "perfecto": 2, "perfecta": 2,
    "recomiendo": 1.5, "recomendable": 1.5, "encanta": 2, "encanto": 2, "rapido": 1, "comodo": 1,
    "facil": 1, "util": 1, "calidad": 0.5, "contento": 1.5, "feliz": 1.5, "funciona": 1, "barato": 0.5,
    "bien": 1, "maravilla": 2, "solido": 1, "good": 1, "great": 2, "excellent": 2, "love": 2,
}
NEGATIVAS = {
    "malo": -1, "mala": -1, "pesimo": -2, "horrible": -2, "terrible": -2, "roto": -1.5, "rota": -1.5,
    "defectuoso": -2, "decepcion": -2, "decepcionante": -2, "lento": -1, "caro": -0.5, "devolvi": -1.5,
    "devolucion": -1, "falla": -1.5, "fallo": -1.5, "nunca": -0.5, "basura": -2, "estafa": -2.5,
    "incomodo": -1, "mal": -1, "dificil": -0.5, "bad": -1, "awful": -2, "broken": -1.5, "waste": -2,
}
# Palabras que invierten el sentido de lo que sigue.
NEGADORES = {"no", "nunca", "ni", "jamas", "tampoco", "sin", "not", "never"}
# Multiplicadores para la palabra siguiente.
INTENSIFICADORES = {"muy": 1.5, "super": 1.5, "re": 1.3, "realmente": 1.3, "totalmente": 1.5, "very": 1.5}


def _tokens(texto: str) -> list[str]:
    """Palabras en minúscula y sin tildes ("Pésimo" → "pesimo")."""
    # NFD separa la letra de su tilde; se descartan las marcas combinantes (categoría "Mn"). La ñ queda como n.
    sin_tildes = "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")
    return re.findall(r"[a-zñ]+", sin_tildes)


def puntuar(texto: str) -> float:
    """Puntaje de sentimiento en [-1, 1] según el algoritmo del docstring del módulo."""
    toks = _tokens(texto)
    total = 0.0
    for i, t in enumerate(toks):
        # Palabras fuera del léxico valen None y se saltan.
        valor = POSITIVAS.get(t) or NEGATIVAS.get(t)
        if not valor or (t == "nunca" and i + 1 < len(toks)):  # "nunca" como negador, no como palabra
            continue
        # Intensificador justo antes de la palabra.
        if i and toks[i - 1] in INTENSIFICADORES:
            valor *= INTENSIFICADORES[toks[i - 1]]
        # Ventana de las 3 palabras previas.
        if any(n in NEGADORES for n in toks[max(0, i - 3):i]):
            valor *= -0.75  # la negación invierte pero suaviza ("no es malo" ≠ "excelente")
        total += valor
    # Normalización suave: crece con el total pero nunca llega a ±1.
    return round(total / math.sqrt(total * total + 4), 3)


def clasificar(puntaje: float, umbral: float = 0.15) -> str:
    """Etiqueta "positiva", "negativa" o "neutral" según el umbral."""
    if puntaje >= umbral:
        return "positiva"
    if puntaje <= -umbral:
        return "negativa"
    return "neutral"
