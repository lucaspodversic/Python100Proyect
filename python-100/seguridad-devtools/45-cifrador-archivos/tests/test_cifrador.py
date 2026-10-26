"""Tests: ida y vuelta, integridad, truncamiento, reordenamiento."""
import io
import os

import pytest

from cifrador import ErrorCifrado, cifrar_archivo, descifrar_archivo, cifrar_flujo, descifrar_flujo
from cifrador.cli import ejecutar
from cifrador.nucleo import LARGO_ENCABEZADO, TAG

N = 2**10  # costo bajo de scrypt sólo para tests
B = 32     # bloques chicos para probar varios bloques con pocos datos


# Ayudantes en memoria (BytesIO): sin archivos y con bloques de 32 bytes.
def cifrar(datos: bytes, clave="clave-segura") -> bytes:
    out = io.BytesIO(); cifrar_flujo(io.BytesIO(datos), out, clave, N, B); return out.getvalue()


def descifrar(blob: bytes, clave="clave-segura") -> bytes:
    out = io.BytesIO(); descifrar_flujo(io.BytesIO(blob), out, clave, B); return out.getvalue()


# Bordes: vacío, 1 byte, justo antes/en/después del tamaño de bloque (32) y varios bloques.
@pytest.mark.parametrize("tam", [0, 1, 31, 32, 33, 64, 1000])
def test_ida_y_vuelta(tam):
    datos = os.urandom(tam)
    assert descifrar(cifrar(datos)) == datos


# Clave equivocada → ErrorCifrado (nunca datos basura).
def test_clave_incorrecta():
    with pytest.raises(ErrorCifrado):
        descifrar(cifrar(b"hola"), "otra")


# Un bit cambiado en el primer bloque cifrado invalida su tag.
def test_bit_alterado():
    blob = bytearray(cifrar(b"x" * 100)); blob[LARGO_ENCABEZADO + 3] ^= 1
    with pytest.raises(ErrorCifrado):
        descifrar(bytes(blob))


# 100 bytes = 3 bloques de 32 + uno de 4; se quita el último y debe detectarse.
def test_truncado_detectado():
    blob = cifrar(b"y" * 100)  # 4 bloques de 32 (el último de 4 bytes)
    sin_ultimo = blob[: LARGO_ENCABEZADO + 3 * (B + TAG)]
    with pytest.raises(ErrorCifrado):
        descifrar(sin_ultimo)


# Intercambiar los bloques 1 y 2: el contador del nonce no coincide.
def test_reordenado_detectado():
    blob = cifrar(b"a" * 32 + b"b" * 32 + b"c")
    enc, cuerpo = blob[:LARGO_ENCABEZADO], blob[LARGO_ENCABEZADO:]
    b1, b2, b3 = cuerpo[:B + TAG], cuerpo[B + TAG:2 * (B + TAG)], cuerpo[2 * (B + TAG):]
    with pytest.raises(ErrorCifrado):
        descifrar(enc + b2 + b1 + b3)


# Magic incorrecto → rechazo inmediato.
def test_encabezado_invalido():
    with pytest.raises(ErrorCifrado):
        descifrar(b"NOPE" + b"\x00" * 40)


# Flujo en disco: no aparece texto plano en el cifrado, no se pisa el destino y un fallo no deja .parcial.
def test_archivos_y_no_deja_parciales(tmp_path):
    src = tmp_path / "doc.txt"; src.write_bytes(b"contenido secreto" * 1000)
    enc = tmp_path / "doc.txt.aesf"; cifrar_archivo(src, enc, "clave-segura", N)
    assert b"secreto" not in enc.read_bytes()
    with pytest.raises(FileExistsError):
        cifrar_archivo(src, enc, "clave-segura", N)
    with pytest.raises(ErrorCifrado):
        descifrar_archivo(enc, tmp_path / "mal.txt", "incorrecta")
    assert not list(tmp_path.glob("*.parcial")) and not (tmp_path / "mal.txt").exists()
    descifrar_archivo(enc, tmp_path / "ok.txt", "clave-segura")
    assert (tmp_path / "ok.txt").read_bytes() == src.read_bytes()


# Nombres por defecto (.aesf ida y vuelta) y exit 2 con clave incorrecta.
def test_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("CIFRADOR_CLAVE", "clave-segura")
    f = tmp_path / "a.bin"; f.write_bytes(b"123")
    assert ejecutar(["cifrar", str(f)], n=N) == 0
    f.unlink()
    assert ejecutar(["descifrar", str(tmp_path / "a.bin.aesf")]) == 0
    assert f.read_bytes() == b"123"
    monkeypatch.setenv("CIFRADOR_CLAVE", "mala")
    assert ejecutar(["descifrar", str(tmp_path / "a.bin.aesf"), "-o", str(tmp_path / "z")]) == 2
