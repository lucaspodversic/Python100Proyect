"""Tests del motor (sin GUI)."""
import math

import pytest

from calc.motor import Calculadora, ErrorCalculo, formatear


@pytest.fixture()
def calc():
    """Calculadora nueva por test (radianes, memoria 0, historial vacío)."""
    return Calculadora()


@pytest.mark.parametrize("expr, esperado", [
    # Precedencia: * antes que +, salvo paréntesis.
    ("2 + 3 * 4", 14), ("(2 + 3) * 4", 20),
    # ^ se traduce a ** ; // y % de Python.
    ("2^10", 1024), ("7 // 2", 3), ("7 % 4", 3),
    # Unarios encadenados: -3 + (+5) = 2.
    ("-3 + +5", 2),
    # sqrt(16)=4, 5!=120 → 124. log es base 10, ln es natural.
    ("sqrt(16) + fact(5)", 124), ("log(1000)", 3), ("ln(e)", 1),
    # Símbolos de la botonera: 2×3÷4 = 6/4 = 1.5.
    ("2 × 3 ÷ 4", 1.5),
    # sin(pi) sería 1.2e-16 sin el redondeo a 12 decimales; cbrt admite negativos.
    ("sin(pi)", 0), ("cbrt(-27)", -3), ("abs(-2.5)", 2.5),
    # π también se redondea a 12 decimales.
    ("π", round(math.pi, 12)),
])
def test_expresiones(calc, expr, esperado):
    """Cada expresión de la tabla da el valor esperado (con tolerancia de punto flotante)."""
    assert calc.evaluar(expr) == pytest.approx(esperado)


def test_modo_grados_y_ans(calc):
    """En modo grados sin(90°)=1 y asin(1)=90°. 'ans' es el último resultado (90), así que
    ans/2=45. El historial guarda los tres resultados en orden.
    """
    calc.grados = True
    assert calc.evaluar("sin(90)") == 1
    assert calc.evaluar("asin(1)") == 90
    assert calc.evaluar("ans / 2") == 45
    assert [v for _, v in calc.historial] == [1, 90, 45]


@pytest.mark.parametrize("expr, mensaje", [
    # Errores matemáticos y de sintaxis.
    ("1/0", "división por cero"), ("sqrt(-1)", "matemático"), ("2 +", "sintaxis"),
    # Intentos de ejecutar código: llamada sobre un atributo → nodo no permitido;
    # open no está en la lista blanca de funciones; x no es una constante conocida.
    ("__import__('os').system('ls')", "no permitida"), ("open('x')", "desconocida"),
    ("x + 1", "desconocido"),
    # Límites anti-DoS: exponente > 10 000 y factorial > 1000; 2.5! no es entero.
    ("9 ** 99999", "exponente"), ("fact(2.5)", "factorial"), ("fact(5000)", "grande"),
    # Vacío; True es una constante bool (no número) y se rechaza a propósito.
    ("", "vacía"), ("True + 1", "no permitida"),
])
def test_errores_y_seguridad(calc, expr, mensaje):
    """Entradas inválidas o maliciosas lanzan ErrorCalculo con un mensaje claro y nunca se
    ejecutan (no hay eval).
    """
    with pytest.raises(ErrorCalculo, match=mensaje):
        calc.evaluar(expr)


def test_memoria(calc):
    """M+ 5, M- 2 → 3; MC → 0."""
    calc.memoria_sumar(5)
    calc.memoria_restar(2)
    assert calc.memoria == 3
    calc.memoria_borrar()
    assert calc.memoria == 0


def test_formatear():
    """Enteros sin '.0'; 0.1+0.2 se muestra 0.3 (12 cifras significativas ocultan el error
    binario); valores enormes o diminutos en notación científica.
    """
    assert formatear(4.0) == "4"
    assert formatear(0.1 + 0.2) == "0.3"
    assert "e" in formatear(1e20) and "e" in formatear(1e-9)
