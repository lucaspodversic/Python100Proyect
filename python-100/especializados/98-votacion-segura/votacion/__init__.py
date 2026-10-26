"""Votación electrónica segura (proyecto didáctico).

Módulos:

* ``cripto``   – firmas ciegas RSA (Chaum) con hash de dominio completo (FDH).
* ``urna``     – urna de votos encadenada por hash (SHA-256), persistida en SQLite.
* ``servicio`` – reglas de la elección: padrón, tokens de un solo uso, estados.
* ``api``      – endpoints FastAPI (``create_app``).
* ``cliente``  – lo que haría el dispositivo del votante (cegar/descegar).
"""
