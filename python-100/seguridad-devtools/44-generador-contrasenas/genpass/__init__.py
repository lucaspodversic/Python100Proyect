"""genpass: generador de contraseñas robustas con `secrets` (CSPRNG)."""
# API pública: opciones, generadores y medidas de entropía/fortaleza.
from .nucleo import Opciones, entropia_bits, generar, generar_frase, fortaleza

__all__ = ["Opciones", "entropia_bits", "generar", "generar_frase", "fortaleza"]
