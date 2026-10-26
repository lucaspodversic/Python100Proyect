"""Tests unitarios de la pasarela simulada."""
from tienda.pagos import PasarelaSimulada, _vencimiento_valido, luhn_valido


def test_luhn():
    # 4242... es la tarjeta de prueba clásica y pasa Luhn; cambiar el último
    # dígito (…41) rompe el verificador; letras nunca son válidas.
    assert luhn_valido("4242424242424242")
    assert not luhn_valido("4242424242424241")
    assert not luhn_valido("abcd")


def test_vencimiento():
    # Con "hoy" fijo en octubre 2026: 12/30 vigente, 09/26 vencida, mes 13 inválido.
    assert _vencimiento_valido("12/30", hoy=(2026, 10))
    assert not _vencimiento_valido("09/26", hoy=(2026, 10))
    assert not _vencimiento_valido("13/30", hoy=(2026, 10))


def test_cobro_aprobado_y_rechazado():
    p = PasarelaSimulada()
    # Con espacios se normaliza y aprueba; 4000000000009995 es "fondos
    # insuficientes"; importe 0 siempre se rechaza.
    ok = p.cobrar(1000, "4242 4242 4242 4242", "123", "12/99")
    assert ok.aprobado and ok.id_transaccion in p.cobros and ok.ultimos4 == "4242"
    no = p.cobrar(1000, "4000000000009995", "123", "12/99")
    assert not no.aprobado and no.motivo == "Fondos insuficientes"
    assert not p.cobrar(0, "4242424242424242", "123", "12/99").aprobado
