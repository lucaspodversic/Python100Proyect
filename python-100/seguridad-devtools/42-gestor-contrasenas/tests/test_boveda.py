"""Tests de cifrado real y de la bóveda (n de scrypt bajo para velocidad)."""
import pytest

from boveda import Boveda, Entrada, ErrorDescifrado, cifrar, descifrar
from boveda.boveda import generar_contrasena
from boveda.cli import ejecutar

N = 2**10  # parámetro de scrypt reducido SOLO para tests


# Cifrar y descifrar devuelve lo mismo, y el texto plano no aparece en el blob.
def test_ida_y_vuelta():
    blob = cifrar(b"secreto", "maestra-123", n=N)
    assert descifrar(blob, "maestra-123") == b"secreto"
    assert b"secreto" not in blob  # el texto plano no aparece


# Mismo texto y misma maestra → blobs distintos (sal y nonce aleatorios).
def test_sal_y_nonce_distintos_cada_vez():
    assert cifrar(b"x", "maestra-123", n=N) != cifrar(b"x", "maestra-123", n=N)


def test_maestra_incorrecta():
    blob = cifrar(b"x", "maestra-123", n=N)
    with pytest.raises(ErrorDescifrado):
        descifrar(blob, "otra-clave")


# Posiciones: 5 = byte de log2(n), 10 = sal, 30 = nonce, -1 = último byte del tag.
@pytest.mark.parametrize("pos", [5, 10, 30, -1])
def test_alteracion_detectada(pos):
    blob = bytearray(cifrar(b"datos importantes", "maestra-123", n=N))
    blob[pos] ^= 0x01  # cambiamos un bit del encabezado o del cifrado
    with pytest.raises(ErrorDescifrado):
        descifrar(bytes(blob), "maestra-123")


# Caso borde: blob más corto que el encabezado.
def test_formato_invalido():
    with pytest.raises(ErrorDescifrado):
        descifrar(b"basura", "x")


# Se guarda, se reabre desde disco y se busca sin distinguir mayúsculas.
def test_boveda_persistencia(tmp_path):
    ruta = tmp_path / "v.bin"
    b = Boveda.crear(ruta, "maestra-123", n_kdf=N)
    b.agregar(Entrada("GitHub", "lucas", "pw1")); b.guardar()
    b2 = Boveda.abrir(ruta, "maestra-123")
    assert b2.obtener("github").contrasena == "pw1"
    assert [e.servicio for e in b2.buscar("git")] == ["GitHub"]


# "A" choca con "a" (claves en minúsculas) salvo que se pida reemplazar.
def test_duplicado_y_eliminar(tmp_path):
    b = Boveda.crear(tmp_path / "v.bin", "maestra-123", n_kdf=N)
    b.agregar(Entrada("a", "u", "p"))
    with pytest.raises(KeyError):
        b.agregar(Entrada("A", "u", "p"))
    b.agregar(Entrada("A", "u2", "p2"), reemplazar=True)
    assert b.obtener("a").usuario == "u2"
    b.eliminar("a")
    assert not b.entradas


# Tras cambiar la maestra la anterior ya no abre la bóveda.
def test_cambiar_maestra(tmp_path):
    ruta = tmp_path / "v.bin"
    b = Boveda.crear(ruta, "maestra-123", n_kdf=N)
    b.cambiar_maestra("nueva-maestra")
    with pytest.raises(ErrorDescifrado):
        Boveda.abrir(ruta, "maestra-123")
    assert Boveda.abrir(ruta, "nueva-maestra").entradas == {}


# Validación de largo mínimo y protección contra sobrescribir.
def test_maestra_corta_y_no_pisa(tmp_path):
    with pytest.raises(ValueError):
        Boveda.crear(tmp_path / "v.bin", "corta")
    Boveda.crear(tmp_path / "w.bin", "maestra-123", n_kdf=N)
    with pytest.raises(FileExistsError):
        Boveda.crear(tmp_path / "w.bin", "maestra-123", n_kdf=N)


# Largo pedido respetado y dos generaciones seguidas distintas.
def test_generar_contrasena():
    assert len(generar_contrasena(32)) == 32
    assert generar_contrasena() != generar_contrasena()


# Flujo completo por CLI con la maestra en variable de entorno (sin getpass interactivo).
def test_cli_flujo(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BOVEDA_MAESTRA", "maestra-123")
    ruta = str(tmp_path / "v.bin")
    assert ejecutar(["--archivo", ruta, "init"], n_kdf=N) == 0
    assert ejecutar(["--archivo", ruta, "add", "mail", "yo", "--generar", "16"], n_kdf=N) == 0
    assert ejecutar(["--archivo", ruta, "list"], n_kdf=N) == 0
    assert "mail\tyo" in capsys.readouterr().out
    # Servicio inexistente → 1; maestra incorrecta → 2.
    assert ejecutar(["--archivo", ruta, "get", "nada"], n_kdf=N) == 1
    monkeypatch.setenv("BOVEDA_MAESTRA", "incorrecta")
    assert ejecutar(["--archivo", ruta, "list"], n_kdf=N) == 2
