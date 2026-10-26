"""Bot de "swipes" demostrativo (Selenium/Page Object) contra una app MOCK local.

No automatiza Tinder ni ninguna app real: hacerlo viola sus términos y
expone la cuenta a un baneo. Todo el flujo corre contra ``sitio_mock``.
"""

# Sólo se exportan las reglas puras; el bot y el mock se importan desde sus módulos.
from .preferencias import Perfil, Preferencias, Veredicto, decidir

__all__ = ["Perfil", "Preferencias", "Veredicto", "decidir"]
