"""Organizador de archivos inteligente.

Expone las piezas principales para usarlas como biblioteca:
- ``clasificar``: decide la carpeta destino de un archivo.
- ``planificar`` / ``ejecutar``: arma y aplica un plan de movimientos.
- ``deshacer``: revierte una ejecución usando el registro JSON.
"""

# Reexportamos la API pública para que el usuario haga ``from organizador import planificar``
# sin conocer la estructura interna de módulos.
from .clasificador import CATEGORIAS, categoria_de, clasificar
from .organizador import Movimiento, deshacer, ejecutar, planificar

# ``__all__`` define qué exporta ``from organizador import *`` y documenta la API estable.
__all__ = [
    "CATEGORIAS",
    "categoria_de",
    "clasificar",
    "Movimiento",
    "planificar",
    "ejecutar",
    "deshacer",
]
