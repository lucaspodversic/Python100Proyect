"""Paquete del sistema de reservas de hotel.

Módulos:
- ``db``: motor SQLAlchemy con transacciones ``BEGIN IMMEDIATE`` (control de concurrencia).
- ``modelos``: tablas ORM (usuarios, tokens, habitaciones, reservas).
- ``esquemas``: modelos Pydantic de entrada/salida de la API.
- ``seguridad``: hash de contraseñas, tokens y control de roles.
- ``servicio``: reglas de negocio (disponibilidad, reservas, cancelaciones).
- ``main``: fábrica de la aplicación FastAPI y rutas HTTP.
"""
