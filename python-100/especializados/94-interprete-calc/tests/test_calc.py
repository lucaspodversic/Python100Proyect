"""Tests de lexer, parser, evaluador, REPL y CLI del mini lenguaje."""
import math

import pytest

from calc import ast as A
from calc.cli import main, repl
from calc.errores import ErrorEjecucion, ErrorLexico, ErrorSintaxis
from calc.evaluador import Interprete, formatear
from calc.lexer import tokenizar
from calc.parser import parsear


def ev(src):
    """Evalúa un programa en un intérprete nuevo."""
    return Interprete().ejecutar(src)


def test_lexer():
    """'1_000' → 1000; '2.5e-1' → 0.25; '//' es un único token; el comentario se ignora; el
    salto de línea es FIN_SENT y el token siguiente está en la línea 2. '$' en la
    columna 3 da un error léxico en 1:3.
    """
    toks = tokenizar("x1 = 1_000 + 2.5e-1 // 3 # comentario\ny<=2")
    assert [(t.tipo, t.valor) for t in toks][:7] == [
        ("ID", "x1"), ("OP", "="), ("NUM", 1000), ("OP", "+"), ("NUM", 0.25), ("OP", "//"), ("NUM", 3)]
    assert toks[7].tipo == "FIN_SENT" and toks[8].linea == 2 and toks[9].valor == "<="
    with pytest.raises(ErrorLexico, match="1:3"):
        tokenizar("2 $ 3")


def test_parser_ast_y_precedencia():
    """'*' enlaza más que '+' (queda a la derecha del '+'); '^' es asociativo a derecha:
    2^(3^2).
    """
    (s,) = parsear("1 + 2 * 3").sentencias
    assert isinstance(s, A.Binario) and s.op == "+" and s.der.op == "*"
    (s,) = parsear("2 ^ 3 ^ 2").sentencias
    assert s.der.op == "^"  # asociativa a derecha


@pytest.mark.parametrize("src, esperado", [
    # Precedencia: * antes que +; los paréntesis la cambian.
    ("1 + 2 * 3", 7), ("(1 + 2) * 3", 9),
    # ^ asociativo a derecha: 2^(3^2) = 2^9 = 512. El '-' prefijo enlaza menos que ^: -(2^2) = -4.
    ("2 ^ 3 ^ 2", 512), ("-2 ^ 2", -4), ("2 ^ -1", 0.5),
    # '/' es división real pero 6/3 da el entero 2 si es exacta; '//' trunca hacia abajo.
    ("7 / 2", 3.5), ("6 / 3", 2), ("7 // 2", 3),
    # Módulo con el signo del divisor (como Python): -7 = 3·(-3) + 2.
    ("-7 % 3", 2),
    ("1 < 2 and not (3 == 4)", True), ("if 2 > 1 then 10 else 20", 10),
    # Internas: sqrt(16) = 4 y max = 5 → 9; round(π, 2) = 3.14; log en base 2 de 8 = 3.
    ("sqrt(16) + max(1, 5, 3)", 9.0), ("round(pi, 2)", 3.14), ("log(8, 2)", 3.0),
    # Enteros de precisión arbitraria (dentro del límite de exponente) y varias sentencias con ';'.
    ("2 ^ 100", 2 ** 100), ("x = 4; y = x * 2; y + 1", 9),
])
def test_evaluacion(src, esperado):
    """Ver los comentarios de la tabla de casos."""
    assert ev(src) == pytest.approx(esperado) if isinstance(esperado, float) else ev(src) == esperado


def test_funciones_recursivas_y_ambito():
    """El parámetro x tapa la global x=100 sin modificarla; fact(20) recursivo da exacto 20!
    (enteros de precisión arbitraria); una función puede leer globales.
    """
    it = Interprete()
    it.ejecutar("x = 100\ndef doble(x) = x * 2\ndef fact(n) = if n <= 1 then 1 else n * fact(n - 1)")
    assert it.ejecutar("doble(5)") == 10 and it.globales["x"] == 100   # el parámetro tapa la global
    assert it.ejecutar("fact(20)") == math.factorial(20)
    assert it.ejecutar("def usaglobal(a) = a + x\nusaglobal(1)") == 101


def test_cortocircuito():
    """El lado derecho daría división por cero, así que estos tests fallarían si se evaluara."""
    # El lado derecho daría división por cero si se evaluara.
    assert ev("false and 1 / 0 == 1") is False
    assert ev("true or 1 / 0 == 1") is True


@pytest.mark.parametrize("src, mensaje", [
    # Errores de valores y nombres.
    ("1 / 0", "división por cero"), ("y + 1", "no definida 'y'"), ("f(1)", "función no definida"),
    # Tipos estrictos: no se suman booleanos y 'if' no acepta números como condición.
    ("1 + true", "necesita números"), ("if 1 then 2 else 3", "booleano"), ("pi = 3", "constante"),
    # Aridad y dominio de las internas; 2^100000 supera MAX_EXPONENTE (10 000).
    ("sqrt(1, 2)", "recibe 1"), ("sqrt(-1)", "sqrt"), ("2 ^ 100000", "exponente"),
    # Recursión infinita cortada en MAX_PROFUNDIDAD (200); raíz de un negativo daría un complejo.
    ("def f(n) = f(n + 1)\nf(0)", "recursión"), ("(-8) ^ 0.5", "complejo"), ("1 == true", "comparar"),
    ("def sqrt(x) = x", "interna"),
])
def test_errores_ejecucion(src, mensaje):
    """Ver los comentarios de la tabla de casos."""
    with pytest.raises(ErrorEjecucion, match=mensaje):
        ev(src)


# "1 +": falta operando en la col 4 (fin). "(1 + 2": falta ')' en la col 7. "x = \n": fin de línea en col 5.
# "1 < 2 < 3": el segundo '<' (col 7). Parámetro repetido: se señala el 'def' (col 1). "2 3": el 3 sobra.
@pytest.mark.parametrize("src, pos", [("1 +", "1:4"), ("(1 + 2", "1:7"), ("x = \n", "1:5"),
                                      ("1 < 2 < 3", "1:7"), ("def f(a, a) = 1", "1:1"), ("2 3", "1:3")])
def test_errores_sintaxis_con_posicion(src, pos):
    """La posición apunta al token problemático (columnas 1-based)."""
    with pytest.raises(ErrorSintaxis, match=pos):
        parsear(src)


def test_error_en_linea_correcta():
    """La división por cero de la línea 3 se informa en la línea 3."""
    with pytest.raises(ErrorEjecucion) as e:
        ev("a = 1\nb = 2\nc = a / (b - 2)")
    assert e.value.linea == 3


def test_formatear():
    """0.1+0.2 = 0.30000000000000004 se muestra '0.3' con 12 cifras significativas."""
    assert formatear(0.1 + 0.2) == "0.3" and formatear(True) == "true" and formatear(None) == ""


def test_repl():
    """Salida esperada: saludo (se descarta), 2, 2^10 = 1024, el error de '1 +' sin cortar el
    REPL, :vars y :funcs. La línea vacía no imprime nada.
    """
    entradas = iter(["x = 2", "x ^ 10", "1 +", ":vars", "def f(a) = a", ":funcs", "", ":salir"])
    salida = []
    repl(lambda _p: next(entradas), salida.append)
    assert salida[1:] == ["2", "1024", "error de sintaxis en 1:4: se esperaba una expresión, se encontró fin de entrada",
                          "x=2", "f(a)"]


def test_cli_archivo_y_expresion(tmp_path, capsys):
    """ejemplos/factorial.calc calcula fact(20) + fib(15) = 20! + 610. '-e 1/0' sale con 1 y el
    mensaje en stderr; un archivo inexistente también da 1.
    """
    from pathlib import Path
    ejemplo = Path(__file__).parent.parent / "ejemplos" / "factorial.calc"
    assert main([str(ejemplo)]) == 0
    assert capsys.readouterr().out.strip() == str(math.factorial(20) + 610)
    assert main(["-e", "1/0"]) == 1
    assert "división por cero" in capsys.readouterr().err
    assert main([str(tmp_path / "no.calc")]) == 1
