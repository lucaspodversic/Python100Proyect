"""Tests del núcleo criptográfico (firmas ciegas RSA + FDH)."""
import pytest

from votacion.cripto import (Autoridad, ClavePublica, cegar, descegar, factor_cegado, fdh, verificar)


def test_fdh_determinista_y_en_rango(autoridad):
    """El FDH es una función: mismo mensaje → mismo número, siempre < n, y
    usa todo el ancho de n (con 1024 bits casi seguro supera 2^256, el tope de un SHA-256 solo)."""
    n = autoridad.publica.n
    assert fdh(b"hola", n) == fdh(b"hola", n)
    assert fdh(b"hola", n) != fdh(b"hola!", n)
    assert 0 <= fdh(b"x", n) < n
    assert fdh(b"x", n).bit_length() > 256


def test_ciclo_completo_de_firma_ciega(autoridad):
    """cegar → firmar → descegar produce exactamente la firma RSA directa m^d mod n."""
    pub = autoridad.publica
    msg = b"papeleta de prueba"
    r = factor_cegado(pub.n)
    cegado = cegar(pub, msg, r)
    firma = descegar(pub, autoridad.firmar_cegado(cegado), r)
    assert verificar(pub, msg, firma)
    assert firma == pow(fdh(msg, pub.n), autoridad._d, pub.n)  # misma firma que sin cegar


def test_la_autoridad_no_ve_el_mensaje(autoridad):
    """El valor cegado no es el hash del mensaje, y dos cegados del mismo mensaje
    con distinto r son distintos (no se pueden correlacionar)."""
    pub = autoridad.publica
    a = cegar(pub, b"m", factor_cegado(pub.n))
    b = cegar(pub, b"m", factor_cegado(pub.n))
    assert a != b and fdh(b"m", pub.n) not in (a, b)


def test_firmas_invalidas(autoridad):
    """Una firma no vale para otro mensaje, ni alterada, ni fuera de rango (0, ≥ n)."""
    pub = autoridad.publica
    r = factor_cegado(pub.n)
    firma = descegar(pub, autoridad.firmar_cegado(cegar(pub, b"a", r)), r)
    assert not verificar(pub, b"b", firma)
    assert not verificar(pub, b"a", firma + 1)
    assert not verificar(pub, b"a", 0) and not verificar(pub, b"a", pub.n)


def test_firmar_rechaza_valores_triviales(autoridad):
    """0, 1 y n no son cegados legítimos (1^d = 1 revelaría poco, pero no tiene sentido firmarlos)."""
    for v in (0, 1, autoridad.publica.n):
        with pytest.raises(ValueError):
            autoridad.firmar_cegado(v)


def test_clave_publica_huella():
    """La huella es estable y depende de n y e (16 hex = 64 bits, solo para inspección visual)."""
    a, b = ClavePublica(3233, 17), ClavePublica(3233, 17)
    assert a.huella() == b.huella() != ClavePublica(3233, 3).huella()
    assert len(a.huella()) == 16 and a.bytes_modulo == 2  # 3233 cabe en 12 bits → 2 bytes


def test_rsa_de_juguete_con_numeros_conocidos():
    """Ejemplo clásico de libro: p=61, q=53 → n=3233, e=17, d=2753.
    Verificamos la aritmética de cegar/descegar con números chicos calculables a mano."""
    pub = ClavePublica(3233, 17)
    m, r, d = 65, 7, 2753
    cegado = m * pow(r, 17, 3233) % 3233
    s_cegada = pow(cegado, d, 3233)
    s = descegar(pub, s_cegada, r)
    assert s == pow(m, d, 3233)       # = firma directa de m
    assert pow(s, 17, 3233) == m       # y verifica con e
