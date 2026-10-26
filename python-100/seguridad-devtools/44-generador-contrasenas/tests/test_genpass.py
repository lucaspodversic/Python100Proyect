"""Tests del generador: propiedades, no valores concretos (es aleatorio)."""
import string

import pytest

from genpass import Opciones, entropia_bits, fortaleza, generar, generar_frase
from genpass.cli import ejecutar
from genpass.nucleo import AMBIGUOS, SIMBOLOS


# 4 es el mínimo con las 4 clases activas: cada carácter debe ser de una clase distinta.
@pytest.mark.parametrize("largo", [4, 16, 64])
def test_largo_y_clases(largo):
    for _ in range(50):  # repetimos para cubrir la aleatoriedad
        s = generar(Opciones(largo=largo))
        assert len(s) == largo
        assert any(c.islower() for c in s) and any(c.isupper() for c in s)
        assert any(c.isdigit() for c in s) and any(c in SIMBOLOS for c in s)


# Con una sola clase la contraseña es sólo dígitos.
def test_solo_digitos():
    s = generar(Opciones(12, minusculas=False, mayusculas=False, simbolos=False))
    assert s.isdigit()


# 50 repeticiones de 40 caracteres: si se colara un ambiguo, saldría con altísima probabilidad.
def test_sin_ambiguos():
    for _ in range(50):
        assert not set(generar(Opciones(40, excluir_ambiguos=True))) & AMBIGUOS


# Largo 2 < 4 clases; ninguna clase; frase de 0 palabras.
def test_errores():
    with pytest.raises(ValueError):
        generar(Opciones(2))
    with pytest.raises(ValueError):
        generar(Opciones(10, False, False, False, False))
    with pytest.raises(ValueError):
        generar_frase(0)


# 200 contraseñas de ~100 bits: una colisión es prácticamente imposible.
def test_unicidad():
    assert len({generar() for _ in range(200)}) == 200


# Separador personalizado y capitalización de cada palabra.
def test_frase():
    f = generar_frase(4, ".", capitalizar=True)
    partes = f.split(".")
    assert len(partes) == 4 and all(p[0].isupper() for p in partes)


# 8 · log2(2) = 8 bits; largo 0 → 0; 16 · log2(94) ≈ 104,9 bits → "muy fuerte".
def test_entropia_y_fortaleza():
    assert entropia_bits(8, 2) == 8
    assert entropia_bits(0, 10) == 0
    assert fortaleza(30) == "débil" and fortaleza(100) == "muy fuerte"
    assert fortaleza(entropia_bits(16, 94)) == "muy fuerte"


# 3 contraseñas de 10 alfanuméricos (sin símbolos); frase con entropía; largo 1 < 3 clases → exit 1.
def test_cli(capsys):
    assert ejecutar(["-l", "10", "-n", "3", "--sin-simbolos"]) == 0
    lineas = capsys.readouterr().out.split()
    assert len(lineas) == 3 and all(len(l) == 10 and l.isalnum() for l in lineas)
    assert ejecutar(["--frase", "3", "--entropia"]) == 0
    assert "bits" in capsys.readouterr().out
    assert ejecutar(["-l", "1"]) == 1
