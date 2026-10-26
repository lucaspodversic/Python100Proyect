"""Motor de la calculadora: evaluador **seguro** de expresiones.

Nunca usa ``eval``: analiza la expresión con :mod:`ast` y recorre el árbol
admitiendo solo números, operadores aritméticos, constantes y una lista
blanca de funciones. Así una entrada como ``__import__('os').system(...)``
es rechazada en lugar de ejecutarse.

Este módulo no importa Tkinter: se puede testear y reutilizar sin pantalla.
"""
from __future__ import annotations

import ast
import math
import operator
from collections.abc import Callable
from dataclasses import dataclass, field


class ErrorCalculo(ValueError):
    """Error de sintaxis o matemático, con mensaje apto para mostrar al usuario."""


MAX_EXPONENTE = 10_000      # evita cálculos gigantes tipo 9**9**9 (DoS)
MAX_FACTORIAL = 1_000

_BINARIOS: dict[type, Callable[[float, float], float]] = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARIOS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
CONSTANTES = {"pi": math.pi, "e": math.e, "tau": math.tau}


def _factorial(x: float) -> float:
    """Factorial acotado. Solo enteros no negativos (2.5! se rechaza en vez de usar la función
    gamma) y como máximo MAX_FACTORIAL para que 'fact(99999)' no congele la interfaz.
    """
    if x != int(x) or x < 0:
        raise ErrorCalculo("factorial solo de enteros no negativos")
    if x > MAX_FACTORIAL:
        raise ErrorCalculo(f"factorial demasiado grande (máx. {MAX_FACTORIAL})")
    return float(math.factorial(int(x)))


@dataclass
class Calculadora:
    """Estado de la calculadora: modo angular, memoria, último resultado e historial."""

    grados: bool = False
    memoria: float = 0.0
    ans: float = 0.0
    historial: list[tuple[str, float]] = field(default_factory=list)

    # ------------------------------------------------------------ funciones
    def _funciones(self) -> dict[str, Callable[..., float]]:
        """Funciones permitidas. Las trigonométricas respetan el modo grados/radianes."""
        a_rad = math.radians if self.grados else (lambda x: x)
        de_rad = math.degrees if self.grados else (lambda x: x)
        return {
            "sin": lambda x: math.sin(a_rad(x)), "cos": lambda x: math.cos(a_rad(x)),
            "tan": lambda x: math.tan(a_rad(x)),
            "asin": lambda x: de_rad(math.asin(x)), "acos": lambda x: de_rad(math.acos(x)),
            "atan": lambda x: de_rad(math.atan(x)),
            "sqrt": math.sqrt, "cbrt": lambda x: math.copysign(abs(x) ** (1 / 3), x),
            "ln": math.log, "log": math.log10, "log2": math.log2, "exp": math.exp,
            "abs": abs, "fact": _factorial, "round": round,
        }

    # ------------------------------------------------------------ evaluación
    def evaluar(self, expresion: str) -> float:
        """Evalúa y guarda en historial. Acepta ``^`` como potencia y ``×``/``÷``."""
        texto = expresion.replace("^", "**").replace("×", "*").replace("÷", "/").replace("π", "pi").strip()
        if not texto:
            raise ErrorCalculo("expresión vacía")
        if len(texto) > 500:
            raise ErrorCalculo("expresión demasiado larga")
        try:
            arbol = ast.parse(texto, mode="eval")
        except SyntaxError as e:
            raise ErrorCalculo("error de sintaxis") from e
        try:
            valor = self._nodo(arbol.body)
        except ZeroDivisionError as e:
            raise ErrorCalculo("división por cero") from e
        except (OverflowError, ValueError) as e:
            if isinstance(e, ErrorCalculo):
                raise
            raise ErrorCalculo("error matemático (dominio o desbordamiento)") from e
        valor = float(valor)
        if math.isnan(valor) or math.isinf(valor):
            raise ErrorCalculo("resultado no finito")
        # Redondeo cosmético para que sin(pi) dé 0 y no 1.2e-16.
        valor = round(valor, 12) + 0.0
        self.ans = valor
        self.historial.append((expresion, valor))
        return valor

    def _nodo(self, n: ast.AST) -> float:
        """Recorre el AST admitiendo solo nodos de la lista blanca."""
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _BINARIOS:
            izq, der = self._nodo(n.left), self._nodo(n.right)
            if isinstance(n.op, ast.Pow) and abs(der) > MAX_EXPONENTE:
                raise ErrorCalculo("exponente demasiado grande")
            return _BINARIOS[type(n.op)](izq, der)
        if isinstance(n, ast.UnaryOp) and type(n.op) in _UNARIOS:
            return _UNARIOS[type(n.op)](self._nodo(n.operand))
        if isinstance(n, ast.Name):
            if n.id == "ans":
                return self.ans
            if n.id in CONSTANTES:
                return CONSTANTES[n.id]
            raise ErrorCalculo(f"nombre desconocido: {n.id}")
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and not n.keywords:
            funcs = self._funciones()
            if n.func.id not in funcs:
                raise ErrorCalculo(f"función desconocida: {n.func.id}")
            return funcs[n.func.id](*(self._nodo(a) for a in n.args))
        raise ErrorCalculo("expresión no permitida")

    # ------------------------------------------------------------ memoria
    def memoria_sumar(self, valor: float) -> None:
        """M+: suma el valor a la memoria."""
        self.memoria += valor

    def memoria_restar(self, valor: float) -> None:
        """M-: resta el valor de la memoria."""
        self.memoria -= valor

    def memoria_borrar(self) -> None:
        """MC: deja la memoria en 0."""
        self.memoria = 0.0


def formatear(valor: float) -> str:
    """Muestra enteros sin ``.0`` y números muy grandes/pequeños en notación científica."""
    if valor == int(valor) and abs(valor) < 1e15:
        return str(int(valor))
    if abs(valor) >= 1e15 or (valor != 0 and abs(valor) < 1e-6):
        return f"{valor:.10e}"
    return f"{valor:.12g}"
