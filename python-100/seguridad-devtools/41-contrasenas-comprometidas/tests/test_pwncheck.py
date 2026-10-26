"""Tests offline: se usa un cliente falso en lugar de la API real."""
import io

import pytest

from pwncheck import comprobar, dividir_hash, sha1_mayusculas
from pwncheck.cli import ejecutar
from pwncheck.nucleo import buscar_sufijo


# Fake del Protocol ClienteRango: los tests nunca hablan con la API real.
class ClienteFalso:
    """Simula la API: guarda los prefijos pedidos para verificar k-anonymity."""

    def __init__(self, filtradas: dict[str, int]):
        self.pedidos: list[str] = []
        # Se guardan hashes (no contraseñas), igual que la base real de HIBP.
        self.tabla: dict[str, int] = {sha1_mayusculas(p): n for p, n in filtradas.items()}

    def consultar_rango(self, prefijo: str) -> str:
        self.pedidos.append(prefijo)
        # Igual que la API: sólo devuelve los sufijos de hashes que comparten el prefijo pedido.
        lineas = [f"{h[5:]}:{n}" for h, n in self.tabla.items() if h.startswith(prefijo)]
        lineas.append("0000000000000000000000000000000000A:0")  # relleno (padding)
        # CRLF como la API real, para probar que el parser tolera el "\r".
        return "\r\n".join(lineas)


def test_sha1_conocido():
    # SHA-1 de "password" es un vector conocido
    assert sha1_mayusculas("password") == "5BAA61E4C9B93F3F0682250B6CF8331B7EE68FD8"


def test_dividir_hash():
    pre, suf = dividir_hash("5BAA61E4C9B93F3F0682250B6CF8331B7EE68FD8")
    assert pre == "5BAA6" and len(suf) == 35


def test_dividir_hash_invalido():
    with pytest.raises(ValueError):
        dividir_hash("abc")


# Caso principal: contraseña filtrada → conteo correcto.
def test_comprometida_y_solo_envia_prefijo():
    cliente = ClienteFalso({"password": 9_000_000})
    r = comprobar("password", cliente)
    assert r.comprometida and r.apariciones == 9_000_000
    # Sólo se envió el prefijo de 5 caracteres
    assert cliente.pedidos == ["5BAA6"]


# Contraseña con emoji: verifica la codificación UTF-8 antes del hash.
def test_no_comprometida():
    r = comprobar("una-frase-larga-y-unica-💡", ClienteFalso({"password": 3}))
    assert not r.comprometida and r.apariciones == 0


# Entradas de relleno (conteo 0) no cuentan; sufijo en minúsculas igual coincide; líneas basura se ignoran.
def test_padding_con_cero_no_cuenta():
    assert buscar_sufijo("ABC:0\nDEF:5", "abc") == 0
    assert buscar_sufijo("basura\nDEF:5", "DEF") == 5


# Caso borde: cadena vacía.
def test_vacia_falla():
    with pytest.raises(ValueError):
        comprobar("", ClienteFalso({}))


# Dos contraseñas por stdin: una filtrada → exit 1.
def test_cli_stdin_codigos_salida():
    salida = io.StringIO()
    code = ejecutar(["--stdin"], ClienteFalso({"123456": 10}), io.StringIO("123456\nsegura-xyz\n"), salida)
    texto = salida.getvalue()
    assert code == 1
    assert "COMPROMETIDA" in texto and "123456" not in texto  # nunca se imprime la contraseña


# Un cliente que falla simula la caída de red: la CLI debe salir con 2 sin traceback.
def test_cli_error_de_red():
    class Roto:
        def consultar_rango(self, prefijo):
            raise ConnectionError("sin red")
    salida = io.StringIO()
    assert ejecutar(["--stdin"], Roto(), io.StringIO("x\n"), salida) == 2
