"""Nodos del árbol de sintaxis abstracta (inmutables)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Nodo:
    """Base de todos los nodos: guarda línea y columna de origen para que los errores de
    ejecución señalen dónde ocurrieron.
    """
    linea: int
    col: int


@dataclass(frozen=True)
class Numero(Nodo):
    """Literal numérico (int si no tiene punto ni exponente, float si los tiene)."""
    valor: int | float


@dataclass(frozen=True)
class Booleano(Nodo):
    """Literal true/false."""
    valor: bool


@dataclass(frozen=True)
class Variable(Nodo):
    """Referencia a una variable (local, global o constante)."""
    nombre: str


@dataclass(frozen=True)
class Unario(Nodo):
    """Operador prefijo: '-', '+' o 'not'."""
    op: str
    operando: Nodo


@dataclass(frozen=True)
class Binario(Nodo):
    """Operador infijo aritmético, de comparación o lógico."""
    op: str
    izq: Nodo
    der: Nodo


@dataclass(frozen=True)
class Si(Nodo):
    """Expresión condicional 'if c then a else b' (siempre tiene las dos ramas porque es una
    expresión).
    """
    cond: Nodo
    entonces: Nodo
    sino: Nodo


@dataclass(frozen=True)
class Llamada(Nodo):
    """Llamada a una función interna o definida por el usuario."""
    nombre: str
    args: tuple[Nodo, ...]


@dataclass(frozen=True)
class Asignacion(Nodo):
    """Sentencia 'nombre = expr' (solo a nivel global)."""
    nombre: str
    valor: Nodo


@dataclass(frozen=True)
class DefFuncion(Nodo):
    """Sentencia 'def f(a, b) = expr': funciones de una sola expresión, posiblemente
    recursivas.
    """
    nombre: str
    params: tuple[str, ...]
    cuerpo: Nodo


@dataclass(frozen=True)
class Programa:
    """Secuencia de sentencias separadas por salto de línea o ';'."""
    sentencias: tuple[Nodo, ...]
