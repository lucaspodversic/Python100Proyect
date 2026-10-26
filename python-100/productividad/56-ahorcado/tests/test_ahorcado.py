"""Tests de lógica pura y del bucle de consola."""
import random

import pytest

from ahorcado import Partida, Resultado, normalizar
from ahorcado.consola import ejecutar, jugar


# Tildes y diéresis desaparecen; la ñ (también mayúscula) se conserva.
def test_normalizar():
    assert [normalizar(c) for c in "ÁéÜñÑ"] == ["a", "e", "u", "ñ", "ñ"]


# "u" revela "ü"; repetir en mayúscula cuenta como repetida y un número es inválido sin costar fallo.
def test_aciertos_tildes_y_mascara():
    p = Partida("Pingüino")
    assert p.intentar("u") is Resultado.ACIERTO
    assert p.mascara() == "_ _ _ _ ü _ _ _"
    assert p.intentar("U") is Resultado.REPETIDA
    assert p.intentar("7") is Resultado.INVALIDA and p.fallos == 0


# En "ñandú" la "n" acierta la segunda n, pero no descubre la ñ.
def test_ene_es_distinta():
    p = Partida("ñandú")
    assert p.intentar("n") is Resultado.ACIERTO  # hay una 'n' normal
    assert "ñ" not in p.intentadas and p.mascara().startswith("_")


# Ganar letra a letra o arriesgando la palabra sin tilde; después del final, intentar es error.
def test_ganar_con_letras_y_con_palabra():
    p = Partida("ala")
    p.intentar("a"); p.intentar("l")
    assert p.gano() and p.terminada()
    q = Partida("función")
    assert q.intentar("funcion") is Resultado.ACIERTO and q.gano()
    with pytest.raises(RuntimeError):
        q.intentar("x")


# 6 fallos → pierde; cada fallo muestra un dibujo distinto y el último tiene las dos piernas.
def test_perder_y_dibujo():
    p = Partida("sol")
    dibujos = set()
    for letra in "abcdef":
        assert p.intentar(letra) is Resultado.FALLO
        dibujos.add(p.dibujo())
    assert p.perdio() and len(dibujos) == 6 and p.fallidas() == list("abcdef")
    assert "/ \\" in p.dibujo()


# 9 letras ocultas; el espacio queda visible (se ve como 3 espacios por el separador).
def test_palabra_con_espacios():
    p = Partida("hola mundo")
    assert p.mascara().count("_") == 9  # el espacio no se adivina
    p.intentar("o")
    assert p.mascara() == "_ o _ _   _ _ _ _ o"


# Partida ganada con entrada falsa; con letras que no aparecen en ninguna fruta se pierde (exit 1).
def test_consola():
    salida = []
    entradas = iter(["s", "o", "x", "l"])
    assert jugar("sol", lambda _: next(entradas), salida.append) is True
    assert "No está." in salida and salida[-1].startswith("¡Ganaste!")
    entradas = iter("jkqwxy")  # ninguna fruta tiene estas letras
    assert ejecutar(["-c", "frutas"], random.Random(0), lambda _: next(entradas), salida.append) == 1
    assert "Categoría: frutas" in salida
