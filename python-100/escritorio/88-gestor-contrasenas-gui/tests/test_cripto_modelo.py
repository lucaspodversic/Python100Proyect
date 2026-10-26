"""Tests de cifrado y modelo. Se usa scrypt con N bajo para que sean rápidos."""
import base64
import json
import os
import stat

import pytest

from boveda.cripto import Cifrador, ErrorBoveda, ParametrosKdf
from boveda.modelo import Boveda, Entrada, entropia_bits, fortaleza, generar

KDF = ParametrosKdf(n=2**10, r=8, p=1)
MAESTRA = "correcto caballo batería grapa"


@pytest.fixture()
def boveda(tmp_path):
    """Bóveda nueva en un directorio temporal, con KDF barato para que los tests sean rápidos."""
    return Boveda.crear(tmp_path / "b.boveda", MAESTRA, KDF)


def test_ida_y_vuelta_y_permisos(boveda):
    """Guardar y reabrir conserva los datos (incluida la ñ). El archivo queda con permisos 0600
    y ni el sitio ni la contraseña aparecen en claro.
    """
    boveda.agregar(Entrada("GitHub", "ana", "s3cr3t-ñ"))
    otra = Boveda.abrir(boveda.ruta, MAESTRA)
    assert otra.entradas[0].clave == "s3cr3t-ñ"
    assert stat.S_IMODE(os.stat(boveda.ruta).st_mode) == 0o600
    contenido = boveda.ruta.read_text()
    assert "s3cr3t" not in contenido and "GitHub" not in contenido  # nada en claro


def test_clave_incorrecta(boveda):
    """Una maestra equivocada da un error claro, no datos basura (GCM detecta la clave
    errónea).
    """
    with pytest.raises(ErrorBoveda, match="incorrecta"):
        Boveda.abrir(boveda.ruta, "otra contraseña larga")


# Campos que un atacante podría tocar: el cifrado, los parámetros de KDF (en la AAD), el nonce y la versión.
@pytest.mark.parametrize("alterar", ["datos", "kdf_n", "nonce", "version"])
def test_alteraciones_detectadas(boveda, alterar):
    """Cambiar un solo bit del cifrado, los parámetros de KDF, el nonce o la versión hace
    fallar la apertura: todo está autenticado.
    """
    cab = json.loads(boveda.ruta.read_text())
    if alterar == "datos":
        b = bytearray(base64.b64decode(cab["datos"])); b[0] ^= 1
        cab["datos"] = base64.b64encode(bytes(b)).decode()
    elif alterar == "kdf_n":
        cab["kdf"]["n"] = 2**11   # la AAD protege los parámetros
    elif alterar == "nonce":
        cab["nonce"] = base64.b64encode(os.urandom(12)).decode()
    else:
        cab["version"] = 99
    boveda.ruta.write_text(json.dumps(cab))
    with pytest.raises(ErrorBoveda):
        Boveda.abrir(boveda.ruta, MAESTRA)


def test_kdf_malicioso_y_archivo_roto(tmp_path):
    """n = 2^30 pediría ~1 TiB de RAM con r=8 → rechazado; n=1000 no es potencia de 2; JSON
    roto → 'dañado'.
    """
    with pytest.raises(ErrorBoveda, match="rango"):
        ParametrosKdf(n=2**30).validar()
    with pytest.raises(ErrorBoveda, match="rango"):
        ParametrosKdf(n=1000).validar()     # no potencia de 2
    with pytest.raises(ErrorBoveda, match="dañado"):
        Cifrador.abrir(b"{no json", MAESTRA)


def test_nonce_nuevo_en_cada_guardado(boveda):
    """Cada guardado usa un nonce distinto (requisito de seguridad de GCM)."""
    n1 = json.loads(boveda.ruta.read_text())["nonce"]
    boveda.guardar()
    assert json.loads(boveda.ruta.read_text())["nonce"] != n1


def test_crear_validaciones(tmp_path, boveda):
    """Maestra demasiado corta y no pisar una bóveda existente."""
    with pytest.raises(ErrorBoveda, match="al menos"):
        Boveda.crear(tmp_path / "x.boveda", "corta", KDF)
    with pytest.raises(ErrorBoveda, match="ya existe"):
        Boveda.crear(boveda.ruta, MAESTRA, KDF)


def test_crud_busqueda_y_reutilizadas(boveda):
    """Búsqueda sin mayúsculas en sitio, usuario y notas, pero NUNCA en contraseñas ('x1' no
    encuentra nada). Banco y correo comparten 'x1' → un grupo de reutilizadas; al
    cambiarla desaparece. El id no es editable.
    """
    a = boveda.agregar(Entrada("Banco", "ana", "x1", notas="cuenta sueldo"))
    boveda.agregar(Entrada("correo", "ana@x", "x1"))
    boveda.agregar(Entrada("Foro", "anon", "zz"))
    assert [e.sitio for e in boveda.buscar("ana")] == ["Banco", "correo"]
    assert [e.sitio for e in boveda.buscar("SUELDO")] == ["Banco"]
    assert boveda.buscar("x1") == []                       # nunca busca en contraseñas
    assert boveda.reutilizadas() == {"grupo 1": ["Banco", "correo"]}
    boveda.actualizar(a.id, clave="nueva")
    assert boveda.reutilizadas() == {}
    with pytest.raises(ValueError):
        boveda.actualizar(a.id, id="hack")
    boveda.eliminar(a.id)
    assert len(Boveda.abrir(boveda.ruta, MAESTRA).entradas) == 2
    with pytest.raises(ValueError):
        boveda.agregar(Entrada(" ", "u", "c"))


def test_cambiar_maestra(boveda):
    """Cambiar la maestra exige la actual, genera sal nueva y la maestra vieja deja de servir."""
    sal = json.loads(boveda.ruta.read_text())["kdf"]["sal"]
    with pytest.raises(ErrorBoveda):
        boveda.cambiar_maestra("equivocada!!", "nueva maestra 123")
    boveda.cambiar_maestra(MAESTRA, "nueva maestra 123")
    assert json.loads(boveda.ruta.read_text())["kdf"]["sal"] != sal
    Boveda.abrir(boveda.ruta, "nueva maestra 123")
    with pytest.raises(ErrorBoveda):
        Boveda.abrir(boveda.ruta, MAESTRA)


def test_generador():
    """Con todo activado incluye mayúsculas, dígitos y símbolos; sin ellos, solo minúsculas;
    puede evitar caracteres ambiguos (Il1O0o); largo mínimo y que 20 generaciones no se
    repitan (usa ``secrets``).
    """
    for _ in range(50):
        c = generar(12)
        assert len(c) == 12 and any(x.isupper() for x in c) and any(x.isdigit() for x in c)
        assert any(not x.isalnum() for x in c)
    assert generar(8, mayusculas=False, digitos=False, simbolos=False).islower()
    assert not set(generar(100, evitar_ambiguos=True)) & set("Il1O0o")
    with pytest.raises(ValueError):
        generar(4)
    assert len({generar() for _ in range(20)}) == 20


@pytest.mark.parametrize("clave, etiqueta", [
    # Lista de comunes y caracteres repetidos: "muy débil" sin importar el largo.
    ("password", "muy débil"), ("aaaaaaaaaaaaaaaa", "muy débil"),
    # Solo minúsculas (26): 6·log2(26) ≈ 28.2 bits (< 30) → muy débil; 8 → 37.6 → débil.
    ("abcdef", "muy débil"), ("abcdefgh", "débil"),
    # Mayús+minús+dígitos (62): 8·log2(62) ≈ 47.6 (< 50) → débil.
    ("Abcdef12", "débil"),
    # Con símbolos el alfabeto es 95: 14·6.57 ≈ 92 → fuerte; 21·6.57 ≈ 138 (≥ 100) → muy fuerte.
    ("Tr0ub4dor&3xyz", "fuerte"), ("x" * 3 + "Kq9!vP2#mZ7$wL4@nB", "muy fuerte"),
])
def test_fortaleza(clave, etiqueta):
    """Ver la tabla de parametrize: cada etiqueta sale de largo × log2(alfabeto)."""
    assert fortaleza(clave) == etiqueta
    assert entropia_bits("") == 0
