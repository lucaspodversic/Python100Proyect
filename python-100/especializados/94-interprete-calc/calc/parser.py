"""Parser descendente con precedencia de operadores (Pratt): tokens → AST.

Gramática (de menor a mayor precedencia)::

    programa   := sentencia (FIN_SENT sentencia)*
    sentencia  := 'def' ID '(' [ID (',' ID)*] ')' '=' expr
                | ID '=' expr
                | expr
    expr       := 'if' expr 'then' expr 'else' expr | binaria
    binaria    : or(1) < and(2) < not(3, prefijo) < comparación(4, no asociativa)
                 < + -(5) < * / // %(6) < - unario(7) < ^(8, asociativo a derecha)
    primario   := NUM | true | false | ID | ID '(' args ')' | '(' expr ')'

Con estas potencias, ``-2^2`` vale ``-4`` (como en matemática) y
``2^3^2`` vale ``2^9``.
"""
from __future__ import annotations

from . import ast as A
from .errores import ErrorSintaxis
from .lexer import Token, tokenizar

# Potencias de enlace izquierdas de los operadores binarios.
BINARIOS = {"or": 1, "and": 2, "==": 4, "!=": 4, "<": 4, "<=": 4, ">": 4, ">=": 4,
            "+": 5, "-": 5, "*": 6, "/": 6, "//": 6, "%": 6, "^": 8}
ASOC_DERECHA = {"^"}
COMPARACIONES = {"==", "!=", "<", "<=", ">", ">="}
BP_NOT, BP_NEG = 3, 7


class Parser:
    """Parser de descenso recursivo con precedencia de operadores (Pratt). Sentencias: def,
    asignación o expresión. La tabla BINARIOS da la fuerza de enlace de cada operador.
    """
    def __init__(self, tokens: list[Token]) -> None:
        """Lista de tokens (termina en EOF) y posición actual."""
        self.toks = tokens
        self.i = 0

    # ---- utilidades ----
    @property
    def actual(self) -> Token:
        """Token actual sin consumirlo."""
        return self.toks[self.i]

    def avanzar(self) -> Token:
        """Consume y devuelve el token actual."""
        t = self.toks[self.i]
        self.i += 1
        return t

    def es(self, tipo: str, valor: object = None) -> bool:
        """True si el token actual es del tipo (y valor) dado."""
        t = self.actual
        return t.tipo == tipo and (valor is None or t.valor == valor)

    def esperar(self, tipo: str, valor: object = None, que: str = "") -> Token:
        """Consume el token esperado o lanza ErrorSintaxis diciendo qué se esperaba y qué se
        encontró, en la posición del token.
        """
        if not self.es(tipo, valor):
            t = self.actual
            visto = "fin de entrada" if t.tipo == "EOF" else "fin de línea" if t.tipo == "FIN_SENT" else repr(t.valor)
            raise ErrorSintaxis(f"se esperaba {que or valor or tipo}, se encontró {visto}", t.linea, t.col)
        return self.avanzar()

    # ---- programa y sentencias ----
    def programa(self) -> A.Programa:
        """Sentencias separadas por FIN_SENT; las líneas vacías se saltean. Dos expresiones
        seguidas sin separador ('2 3') son un error.
        """
        sentencias = []
        while not self.es("EOF"):
            if self.es("FIN_SENT"):
                self.avanzar()
                continue
            sentencias.append(self.sentencia())
            if not self.es("EOF"):
                self.esperar("FIN_SENT", que="fin de sentencia")
        return A.Programa(tuple(sentencias))

    def sentencia(self) -> A.Nodo:
        """'def nombre(params) = expr' (sin parámetros repetidos), 'nombre = expr' (detectado
        mirando un token adelante) o una expresión suelta.
        """
        t = self.actual
        if self.es("KW", "def"):
            self.avanzar()
            nombre = self.esperar("ID", que="nombre de función").valor
            self.esperar("OP", "(")
            params: list[str] = []
            if not self.es("OP", ")"):
                params.append(self.esperar("ID", que="parámetro").valor)
                while self.es("OP", ","):
                    self.avanzar()
                    params.append(self.esperar("ID", que="parámetro").valor)
            self.esperar("OP", ")")
            if len(set(params)) != len(params):
                raise ErrorSintaxis("parámetros repetidos", t.linea, t.col)
            self.esperar("OP", "=")
            return A.DefFuncion(t.linea, t.col, nombre, tuple(params), self.expr())
        if self.es("ID") and self.toks[self.i + 1].tipo == "OP" and self.toks[self.i + 1].valor == "=":
            self.avanzar(); self.avanzar()
            return A.Asignacion(t.linea, t.col, t.valor, self.expr())
        return self.expr()

    # ---- expresiones (Pratt) ----
    def expr(self, min_bp: int = 0) -> A.Nodo:
        """Bucle de Pratt: parsea un prefijo y, mientras el operador siguiente enlace con
        fuerza ≥ min_bp, lo consume y parsea el lado derecho. Prohíbe encadenar
        comparaciones (1 < 2 < 3) porque su significado es ambiguo.
        """
        izq = self.prefijo()
        while True:
            t = self.actual
            op = t.valor if t.tipo in ("OP", "KW") else None
            bp = BINARIOS.get(op) if isinstance(op, str) else None
            # Izquierda: el lado derecho se parsea con bp+1 (el mismo operador corta);
            # derecha (^): con bp, así el mismo operador sigue enlazando hacia la derecha.
            if bp is None or bp < min_bp:
                break
            self.avanzar()
            der = self.expr(bp if op in ASOC_DERECHA else bp + 1)
            if op in COMPARACIONES and self.actual.valor in COMPARACIONES and self.actual.tipo == "OP":
                raise ErrorSintaxis("las comparaciones no se encadenan; usá 'and'", self.actual.linea, self.actual.col)
            izq = A.Binario(t.linea, t.col, op, izq, der)
        return izq

    def prefijo(self) -> A.Nodo:
        """Lo que puede iniciar una expresión: número, true/false, not, signo, if-then-else,
        paréntesis, variable o llamada. El '-' prefijo enlaza con fuerza 7, menos
        que '^' (8), así -2^2 = -(2^2).
        """
        t = self.avanzar()
        if t.tipo == "NUM":
            return A.Numero(t.linea, t.col, t.valor)
        if t.tipo == "KW" and t.valor in ("true", "false"):
            return A.Booleano(t.linea, t.col, t.valor == "true")
        if t.tipo == "KW" and t.valor == "not":
            return A.Unario(t.linea, t.col, "not", self.expr(BP_NOT))
        if t.tipo == "OP" and t.valor in "+-":
            return A.Unario(t.linea, t.col, t.valor, self.expr(BP_NEG))
        if t.tipo == "KW" and t.valor == "if":
            cond = self.expr()
            self.esperar("KW", "then")
            entonces = self.expr()
            self.esperar("KW", "else")
            return A.Si(t.linea, t.col, cond, entonces, self.expr())
        if t.tipo == "OP" and t.valor == "(":
            e = self.expr()
            self.esperar("OP", ")", que="')'")
            return e
        if t.tipo == "ID":
            if self.es("OP", "("):
                self.avanzar()
                args: list[A.Nodo] = []
                if not self.es("OP", ")"):
                    args.append(self.expr())
                    while self.es("OP", ","):
                        self.avanzar()
                        args.append(self.expr())
                self.esperar("OP", ")", que="')'")
                return A.Llamada(t.linea, t.col, t.valor, tuple(args))
            return A.Variable(t.linea, t.col, t.valor)
        visto = "fin de entrada" if t.tipo == "EOF" else "fin de línea" if t.tipo == "FIN_SENT" else repr(t.valor)
        raise ErrorSintaxis(f"se esperaba una expresión, se encontró {visto}", t.linea, t.col)


def parsear(fuente: str) -> A.Programa:
    """Atajo: tokeniza y parsea un programa completo."""
    return Parser(tokenizar(fuente)).programa()
