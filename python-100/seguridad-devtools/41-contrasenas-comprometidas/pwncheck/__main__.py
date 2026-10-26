"""Permite ejecutar `python -m pwncheck`."""
# Delegamos en la CLI para que `python -m pwncheck` y el script instalado se comporten igual.
from .cli import main

main()
