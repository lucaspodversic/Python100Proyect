"""Analizador léxico: texto → lista de :class:`Token`.

Tokens del lenguaje:

* números: ``42``, ``3.14``, ``1e-3``, ``1_000``;
* identificadores y palabras clave: ``def if then else and or not true false``;
* operadores: ``+ - * / // % ^ = == != < <= > >= ( ) ,``;
* separador de sentencias: salto de línea o ``;``;
* comentarios: desde ``#`` hasta el fin de línea.
"""
from __future__ import annotations

from dataclasses import dataclass

from .errores import ErrorLexico

PALABRAS_CLAVE = {"def", "if", "then", "else", "and", "or", "not", "true", "false"}
# Ordenados de más largo a más corto para que "<=" gane a "<".
OPERADORES = ("//", "==", "!=", "<=", ">=", "+", "-", "*", "/", "%", "^", "=", "<", ">", "(", ")", ",")


@dataclass(frozen=True)
class Token:
    """Token con tipo, valor ya convertido (int/float para NUM) y posición 1-based."""
    tipo: str          # NUM, ID, KW, OP, FIN_SENT, EOF
    valor: object
    linea: int
    col: int


def tokenizar(fuente: str) -> list[Token]:
    """Lexer escrito a mano, un carácter a la vez, siguiendo línea y columna. Ignora espacios y
    comentarios '#'. Salto de línea y ';' terminan sentencias. Números con '_' como
    separador, decimales y exponente. Operadores de dos caracteres antes que los de uno
    ('//', '<='). Cualquier otro carácter es ErrorLexico con su posición.
    """
    toks: list[Token] = []
    i, linea, ini_linea = 0, 1, 0
    n = len(fuente)
    while i < n:
        c = fuente[i]
        col = i - ini_linea + 1
        if c in " \t\r":
            i += 1
        elif c == "#":
            while i < n and fuente[i] != "\n":
                i += 1
        elif c in "\n;":
            toks.append(Token("FIN_SENT", c, linea, col))
            if c == "\n":
                linea, ini_linea = linea + 1, i + 1
            i += 1
        elif c.isdigit() or (c == "." and i + 1 < n and fuente[i + 1].isdigit()):
            j = i
            while j < n and (fuente[j].isdigit() or fuente[j] in "._"):
                j += 1
            if j < n and fuente[j] in "eE":  # exponente
                k = j + 1
                if k < n and fuente[k] in "+-":
                    k += 1
                if k < n and fuente[k].isdigit():
                    j = k
                    while j < n and fuente[j].isdigit():
                        j += 1
            texto = fuente[i:j]
            try:
                valor: object = int(texto) if texto.replace("_", "").isdigit() else float(texto)
            except ValueError:
                raise ErrorLexico(f"número mal formado: {texto!r}", linea, col) from None
            toks.append(Token("NUM", valor, linea, col))
            i = j
        elif c.isalpha() or c == "_":
            j = i
            while j < n and (fuente[j].isalnum() or fuente[j] == "_"):
                j += 1
            palabra = fuente[i:j]
            toks.append(Token("KW" if palabra in PALABRAS_CLAVE else "ID", palabra, linea, col))
            i = j
        else:
            for op in OPERADORES:
                if fuente.startswith(op, i):
                    toks.append(Token("OP", op, linea, col))
                    i += len(op)
                    break
            else:
                raise ErrorLexico(f"carácter inesperado {c!r}", linea, col)
    toks.append(Token("EOF", None, linea, i - ini_linea + 1))
    return toks
