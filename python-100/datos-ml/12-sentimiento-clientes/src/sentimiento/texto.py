"""Normalización de texto en español informal.

Pasos (en orden):
1. minúsculas y sin tildes ("Excelente atención" == "excelente atencion");
2. URLs, menciones y números -> fichas genéricas;
3. letras repetidas reducidas ("buenisimoooo" -> "buenisimoo");
4. **negación**: las palabras que siguen a "no/nunca/ni/tampoco/sin" (hasta
   un signo de puntuación) reciben el prefijo ``no_``. Así "no me gustó" y
   "me gustó" generan rasgos distintos, algo clave para un modelo bolsa-de-palabras.
"""

from __future__ import annotations

import re
import unicodedata

# "jamas" sin tilde porque la negación se aplica después de quitar tildes.
NEGADORES = {"no", "nunca", "ni", "tampoco", "sin", "jamas"}
# Palabras funcionales que no "consumen" la ventana de negación.
_TRANSPARENTES = {"me", "te", "se", "lo", "la", "le", "les", "nos", "muy", "tan", "es", "fue", "era", "estuvo", "esta"}


def sin_tildes(t: str) -> str:
    # NFD separa "á" en "a" + tilde combinante (categoría Mn) y se descartan las Mn.
    # Efecto colateral: "ñ" → "n" (aceptable para un modelo bolsa-de-palabras).
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def normalizar(texto: str, ventana: int = 3) -> str:
    t = sin_tildes(texto.lower())
    t = re.sub(r"https?://\S+", " URL ", t)
    t = re.sub(r"@\w+", " USUARIO ", t)
    # "1.500" o "3,5" → NUM: el valor exacto no aporta al sentimiento y evita miles de rasgos únicos.
    t = re.sub(r"\d+([.,]\d+)?", " NUM ", t)
    # Tres o más letras iguales → dos ("buenooooo" → "buenoo"): conserva el énfasis como rasgo
    # distinto de "bueno" pero unifica todas las longitudes.
    t = re.sub(r"(\w)\1{2,}", r"\1\1", t)
    salida: list[str] = []
    restantes = 0  # cuántas palabras más quedan negadas
    # Tokens = palabras o signos de puntuación; la puntuación corta la ventana de negación.
    for tok in re.findall(r"\w+|[.,;:!?¡¿]", t):
        if tok in ".,;:!?¡¿":
            restantes = 0
            continue
        # El negador se conserva tal cual y abre una ventana de 3 palabras "con contenido".
        if tok in NEGADORES:
            restantes = ventana
            salida.append(tok)
            continue
        if restantes:
            salida.append(f"no_{tok}")
            # Pronombres y verbos auxiliares se marcan pero no gastan ventana: en "no me gustó"
            # "me" no consume y "gustó" queda dentro (no_gusto).
            if tok not in _TRANSPARENTES:
                restantes -= 1
        else:
            salida.append(tok)
    return " ".join(salida)
