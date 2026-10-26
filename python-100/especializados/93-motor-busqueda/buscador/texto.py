"""Análisis de texto en español: normalización, tokens, stopwords y un stemmer ligero.

* Se pliegan las tildes (``canción`` → ``cancion``) y se pasa a minúsculas.
* El stemmer recorta sufijos frecuentes (plurales, -mente, -ción, -ando…),
  de modo que ``programación``, ``programaciones`` y ``programar`` comparten
  raíz. Es deliberadamente simple: prefiere recortar poco a confundir
  palabras distintas.
* :func:`tokens_con_posicion` conserva la posición de cada token, necesaria
  para las búsquedas por frase exacta.
"""
from __future__ import annotations

import re
import unicodedata

_PALABRA = re.compile(r"\w+", re.UNICODE)

STOPWORDS = frozenset("""
a al algo algunas algunos ante antes como con contra cual cuando de del desde donde durante e el ella ellas
ellos en entre era es esa esas ese eso esos esta estas este esto estos fue fueron ha han hasta hay la las le les
lo los mas me mi mis mucho muy ni no nos o os otra otro para pero poco por porque que quien se sea ser si sin
sobre su sus tambien tanto te tiene tu tus u un una uno unos y ya yo the of and to in is for on
""".split())

# Sufijos de mayor a menor longitud; se aplica el primero que deje una raíz de 3+ letras.
SUFIJOS = ("amientos", "imientos", "aciones", "uciones", "amiento", "imiento", "adoras", "adores", "idades",
           "mente", "ancias", "encias", "acion", "ucion", "adora", "ador", "ante", "ando", "iendo", "ancia",
           "encia", "idad", "ivas", "ivos", "able", "ible", "osas", "osos", "aron", "ieron", "ar", "er", "ir",
           "iva", "ivo", "osa", "oso", "es", "as", "os", "a", "o", "e", "s")
MIN_RAIZ = 3


def plegar(texto: str) -> str:
    """Minúsculas y sin diacríticos (la ñ se conserva: no es una tilde)."""
    texto = texto.lower().replace("ñ", "\0")
    sin = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    return sin.replace("\0", "ñ")


def raiz(palabra: str) -> str:
    """Raíz aproximada. Espera una palabra ya pasada por :func:`plegar`."""
    for s in SUFIJOS:
        if palabra.endswith(s) and len(palabra) - len(s) >= MIN_RAIZ:
            return palabra[: -len(s)]
    return palabra


def tokens_con_posicion(texto: str, stem: bool = True) -> list[tuple[str, int]]:
    """(término, posición) de cada palabra que no es stopword.

    La posición cuenta **todas** las palabras, stopwords incluidas, para que una
    frase como "base de datos" exija adyacencia real.
    """
    res = []
    for pos, m in enumerate(_PALABRA.finditer(plegar(texto))):
        w = m.group()
        if w in STOPWORDS or w.isdigit() and len(w) > 12:
            continue
        res.append((raiz(w) if stem else w, pos))
    return res


def terminos(texto: str) -> list[str]:
    """Solo los términos (sin posiciones) de un texto ya normalizado."""
    return [t for t, _ in tokens_con_posicion(texto)]
