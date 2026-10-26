"""Evaluador del AST (intérprete de recorrido de árbol).

Semántica:

* Números enteros de precisión arbitraria y flotantes. ``/`` devuelve entero
  si la división es exacta (``6/3 → 2``); ``//`` es división entera.
* Booleanos separados de los números: ``1 + true`` es error, y ``if`` y
  ``and``/``or`` exigen booleanos, que además cortocircuitan.
* Funciones de usuario: ``def f(x) = …``. Al llamarlas, los parámetros tapan a
  las globales, que solo se leen (no hay efectos laterales). Se permite
  recursión, con un límite de profundidad.
* Constantes protegidas: ``pi`` y ``e``. Funciones internas: ``sqrt``,
  ``abs``, ``min``, ``max``, ``round``, ``floor``, ``ceil``, ``sin``,
  ``cos``, ``tan``, ``log``, ``exp``.
* Límites contra abusos: exponente entero máximo, tamaño de los enteros y
  profundidad de recursión.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from . import ast as A
from .errores import ErrorEjecucion
from .parser import parsear

Valor = int | float | bool
MAX_PROFUNDIDAD = 200
MAX_EXPONENTE = 10_000
MAX_BITS = 100_000

CONSTANTES: dict[str, float] = {"pi": math.pi, "e": math.e}


@dataclass(frozen=True)
class Interna:
    """Función interna: la implementación de Python y su aridad (mínimo, máximo)."""
    fn: Callable[..., Valor]
    aridad: tuple[int, int]   # (mín, máx) argumentos


INTERNAS: dict[str, Interna] = {
    "sqrt": Interna(math.sqrt, (1, 1)), "abs": Interna(abs, (1, 1)),
    "min": Interna(min, (1, 99)), "max": Interna(max, (1, 99)),
    "round": Interna(lambda x, n=0: round(x, int(n)) if n else round(x), (1, 2)),
    "floor": Interna(math.floor, (1, 1)), "ceil": Interna(math.ceil, (1, 1)),
    "sin": Interna(math.sin, (1, 1)), "cos": Interna(math.cos, (1, 1)), "tan": Interna(math.tan, (1, 1)),
    "log": Interna(lambda x, b=math.e: math.log(x, b), (1, 2)), "exp": Interna(math.exp, (1, 1)),
}


def _es_num(v: object) -> bool:
    """True para int/float pero NO para bool (en Python bool es subclase de int y así 'true +
    1' daría 2).
    """
    return isinstance(v, (int, float)) and not isinstance(v, bool)


class Interprete:
    """Evaluador recorriendo el AST. Variables globales y funciones persisten entre llamadas a
    ``ejecutar`` (útil para el REPL). Lleva la profundidad de recursión para cortar
    antes del límite de Python.
    """
    def __init__(self) -> None:
        """Estado vacío: sin variables, sin funciones y profundidad 0."""
        self.globales: dict[str, Valor] = {}
        self.funciones: dict[str, A.DefFuncion] = {}
        self._prof = 0

    def ejecutar(self, fuente: str) -> Valor | None:
        """Ejecuta un programa y devuelve el valor de la última sentencia de expresión."""
        ultimo: Valor | None = None
        for s in parsear(fuente).sentencias:
            ultimo = self.sentencia(s)
        return ultimo

    def sentencia(self, s: A.Nodo) -> Valor | None:
        """Asignación (no se pueden pisar constantes como pi), definición (no se pueden
        redefinir internas) o expresión. Devuelve el valor (None para def).
        """
        if isinstance(s, A.Asignacion):
            if s.nombre in CONSTANTES:
                raise ErrorEjecucion(f"'{s.nombre}' es una constante", s.linea, s.col)
            self.globales[s.nombre] = v = self.eval(s.valor, {})
            return v
        if isinstance(s, A.DefFuncion):
            if s.nombre in INTERNAS:
                raise ErrorEjecucion(f"no se puede redefinir la función interna '{s.nombre}'", s.linea, s.col)
            self.funciones[s.nombre] = s
            return None
        return self.eval(s, {})

    # ---------- expresiones ----------
    def eval(self, n: A.Nodo, local: dict[str, Valor]) -> Valor:
        """Despacho por tipo de nodo: Binario → ``_eval_Binario``, etc."""
        metodo = getattr(self, f"_eval_{type(n).__name__}")
        return metodo(n, local)

    def _eval_Numero(self, n: A.Numero, local) -> Valor:
        """Un literal se evalúa a sí mismo."""
        return n.valor

    def _eval_Booleano(self, n: A.Booleano, local) -> Valor:
        """Un literal se evalúa a sí mismo."""
        return n.valor

    def _eval_Variable(self, n: A.Variable, local) -> Valor:
        """Busca primero en parámetros locales, después en globales y por último en constantes,
        así un parámetro tapa una global del mismo nombre.
        """
        for ambito in (local, self.globales, CONSTANTES):
            if n.nombre in ambito:
                return ambito[n.nombre]
        raise ErrorEjecucion(f"variable no definida '{n.nombre}'", n.linea, n.col)

    def _num(self, v: Valor, n: A.Nodo, op: str) -> int | float:
        """Exige un número, con un error que dice qué operador lo pedía y qué recibió."""
        if not _es_num(v):
            raise ErrorEjecucion(f"'{op}' necesita números, recibió {_tipo(v)}", n.linea, n.col)
        return v

    def _bool(self, v: Valor, n: A.Nodo, que: str) -> bool:
        """Exige un booleano: no hay valores 'truthy' (if 1 es un error, no un true implícito)."""
        if not isinstance(v, bool):
            raise ErrorEjecucion(f"{que} necesita un booleano, recibió {_tipo(v)}", n.linea, n.col)
        return v

    def _eval_Unario(self, n: A.Unario, local) -> Valor:
        """'not' sobre booleanos; '-' y '+' sobre números."""
        v = self.eval(n.operando, local)
        if n.op == "not":
            return not self._bool(v, n, "'not'")
        v = self._num(v, n, n.op)
        return -v if n.op == "-" else v

    def _eval_Si(self, n: A.Si, local) -> Valor:
        """Evalúa solo la rama elegida: así la recursión con caso base termina."""
        cond = self._bool(self.eval(n.cond, local), n, "'if'")
        return self.eval(n.entonces if cond else n.sino, local)

    def _eval_Binario(self, n: A.Binario, local) -> Valor:
        """and/or con cortocircuito (el lado derecho puede no evaluarse). ==/!= comparan
        valores del mismo tipo; el resto exige números. La aritmética controla
        división por cero, exponentes enteros gigantes y potencias que darían un
        complejo.
        """
        op = n.op
        if op in ("and", "or"):  # cortocircuito
            a = self._bool(self.eval(n.izq, local), n, f"'{op}'")
            if (op == "and" and not a) or (op == "or" and a):
                return a
            return self._bool(self.eval(n.der, local), n, f"'{op}'")
        a, b = self.eval(n.izq, local), self.eval(n.der, local)
        if op in ("==", "!="):
            if _es_num(a) != _es_num(b):
                raise ErrorEjecucion("no se puede comparar un número con un booleano", n.linea, n.col)
            return (a == b) if op == "==" else (a != b)
        a, b = self._num(a, n, op), self._num(b, n, op)
        try:
            if op == "+": r = a + b
            elif op == "-": r = a - b
            elif op == "*": r = a * b
            elif op == "/":
                r = a // b if isinstance(a, int) and isinstance(b, int) and a % b == 0 else a / b
            elif op == "//": r = a // b
            elif op == "%": r = a % b
            elif op == "^":
                if isinstance(b, int) and abs(b) > MAX_EXPONENTE:
                    raise ErrorEjecucion(f"exponente demasiado grande (máx. {MAX_EXPONENTE})", n.linea, n.col)
                r = a ** b
                if isinstance(r, complex):
                    raise ErrorEjecucion("resultado complejo (raíz de un negativo)", n.linea, n.col)
            elif op == "<": r = a < b
            elif op == "<=": r = a <= b
            elif op == ">": r = a > b
            elif op == ">=": r = a >= b
            else:  # pragma: no cover - el parser no genera otros
                raise ErrorEjecucion(f"operador desconocido {op}", n.linea, n.col)
        except ZeroDivisionError:
            raise ErrorEjecucion("división por cero", n.linea, n.col) from None
        except OverflowError:
            raise ErrorEjecucion("desbordamiento numérico", n.linea, n.col) from None
        if isinstance(r, int) and not isinstance(r, bool) and r.bit_length() > MAX_BITS:
            raise ErrorEjecucion("entero demasiado grande", n.linea, n.col)
        return r

    def _eval_Llamada(self, n: A.Llamada, local) -> Valor:
        """Internas: valida aridad y tipos y traduce errores de math (dominio, overflow). De
        usuario: valida aridad, arma el ámbito local con los parámetros y controla
        la profundidad de recursión.
        """
        args = [self.eval(a, local) for a in n.args]
        if n.nombre in INTERNAS:
            f = INTERNAS[n.nombre]
            if not f.aridad[0] <= len(args) <= f.aridad[1]:
                raise ErrorEjecucion(f"'{n.nombre}' recibe {_aridad(f.aridad)} argumento(s), recibió {len(args)}",
                                     n.linea, n.col)
            for a in args:
                self._num(a, n, n.nombre)
            try:
                return f.fn(*args)
            except (ValueError, OverflowError) as e:
                raise ErrorEjecucion(f"{n.nombre}: {e}", n.linea, n.col) from None
        if n.nombre not in self.funciones:
            raise ErrorEjecucion(f"función no definida '{n.nombre}'", n.linea, n.col)
        d = self.funciones[n.nombre]
        if len(args) != len(d.params):
            raise ErrorEjecucion(f"'{n.nombre}' recibe {len(d.params)} argumento(s), recibió {len(args)}",
                                 n.linea, n.col)
        if self._prof >= MAX_PROFUNDIDAD:
            raise ErrorEjecucion(f"recursión demasiado profunda (máx. {MAX_PROFUNDIDAD})", n.linea, n.col)
        self._prof += 1
        try:
            return self.eval(d.cuerpo, dict(zip(d.params, args)))
        finally:
            self._prof -= 1


def _tipo(v: object) -> str:
    """Nombre del tipo para los mensajes de error."""
    return "booleano" if isinstance(v, bool) else "número"


def _aridad(a: tuple[int, int]) -> str:
    """'1' o '1–3' para los mensajes de aridad."""
    return str(a[0]) if a[0] == a[1] else f"{a[0]}–{a[1]}"


def formatear(v: Valor | None) -> str:
    """Valor para mostrar: true/false, floats con 12 cifras significativas (0.1+0.2 se ve 0.3)
    y '' para None.
    """
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return f"{v:.12g}"
    return str(v)
