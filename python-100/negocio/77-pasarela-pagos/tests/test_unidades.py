"""Tests unitarios de firma de webhooks y simulación de tarjetas."""
from app import tarjetas, webhooks


def test_firma_valida_y_manipulada():
    cuerpo = b'{"id":"evt_1"}'
    cab = webhooks.firmar("secreto", cuerpo, 1_000)
    assert webhooks.verificar("secreto", cuerpo, cab, ahora=1_100)
    assert not webhooks.verificar("otro", cuerpo, cab, ahora=1_100)            # secreto incorrecto
    assert not webhooks.verificar("secreto", b'{"id":"evt_2"}', cab, ahora=1_100)  # cuerpo alterado
    assert not webhooks.verificar("secreto", cuerpo, cab, ahora=1_000 + 301)   # repetición tardía
    assert not webhooks.verificar("secreto", cuerpo, "basura", ahora=1_000)    # mal formada


def test_luhn_y_procesar():
    assert tarjetas.luhn_valido("4242424242424242")
    assert not tarjetas.luhn_valido("4242424242424241")
    assert not tarjetas.luhn_valido("abcd")
    ok = tarjetas.procesar("4242 4242 4242 4242", 12, 2030, (2026, 1))
    assert ok.aprobado and ok.ultimos4 == "4242" and ok.marca == "visa"
    assert tarjetas.procesar("4000000000000002", 12, 2030, (2026, 1)).motivo == "tarjeta_rechazada"
    assert tarjetas.procesar("5555555555554444", 12, 2025, (2026, 1)).motivo == "tarjeta_vencida"
