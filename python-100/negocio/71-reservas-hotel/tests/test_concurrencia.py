"""Prueba de concurrencia: muchos hilos intentan reservar lo mismo a la vez.

Solo uno debe ganar. Sin ``BEGIN IMMEDIATE`` varios hilos podrían pasar la
comprobación de solapamiento antes de que ninguno inserte (condición de carrera).
"""
from __future__ import annotations

import threading
from datetime import date

from sqlalchemy import func, select

from app import servicio
from app.db import Base, crear_fabrica_sesiones, crear_motor
from app.modelos import Habitacion, Reserva, Usuario


def test_reservas_simultaneas_sin_doble_venta(tmp_path):
    motor = crear_motor(f"sqlite:///{tmp_path / 'c.db'}")
    Base.metadata.create_all(motor)
    fabrica = crear_fabrica_sesiones(motor)
    with fabrica.begin() as s:
        s.add(Habitacion(numero="1", tipo="simple", capacidad=1, precio_noche_centavos=100))
        for i in range(12):
            s.add(Usuario(email=f"u{i}@m.com", nombre="u", password_hash="x"))

    exitos: list[int] = []
    errores: list[int] = []
    barrera = threading.Barrier(12)  # arrancan todos a la vez

    def intentar(uid: int) -> None:
        barrera.wait()
        try:
            with fabrica.begin() as s:
                usuario = s.get(Usuario, uid)
                servicio.crear_reserva(s, usuario, 1, date(2026, 7, 1), date(2026, 7, 5), 1, date(2026, 1, 1))
            exitos.append(uid)
        except servicio.ErrorNegocio as e:
            errores.append(e.codigo)

    hilos = [threading.Thread(target=intentar, args=(i + 1,)) for i in range(12)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert len(exitos) == 1
    assert errores == [409] * 11
    with fabrica() as s:
        assert s.scalar(select(func.count()).select_from(Reserva)) == 1
    motor.dispose()
