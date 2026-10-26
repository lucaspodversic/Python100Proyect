"""Tests unitarios de códigos y validaciones."""
import pytest

from acortador.codigos import a_base62, codigo_aleatorio, desde_base62, validar_alias, validar_url


# Casos borde: 0 (caso especial), 61/62 (cambio de 1 a 2 dígitos),
# 3844 = 62² (cambio a 3 dígitos) y un número grande.
@pytest.mark.parametrize("n", [0, 1, 61, 62, 3844, 10**12])
def test_base62_ida_y_vuelta(n):
    assert desde_base62(a_base62(n)) == n


# 7 caracteres alfanuméricos por defecto.
def test_codigo_aleatorio():
    c = codigo_aleatorio()
    assert len(c) == 7 and c.isalnum()


# Esquemas peligrosos, no http, texto suelto y http sin host.
@pytest.mark.parametrize("mala", ["javascript:alert(1)", "data:text/html,x", "ftp://x.com", "no-es-url", "http://"])
def test_urls_peligrosas_rechazadas(mala):
    with pytest.raises(ValueError):
        validar_url(mala)


# "ab" es corto (<3), "docs" reservado, "con espacio" tiene un espacio.
def test_alias():
    assert validar_alias("mi-link") == "mi-link"
    for malo in ("ab", "docs", "con espacio"):
        with pytest.raises(ValueError):
            validar_alias(malo)
