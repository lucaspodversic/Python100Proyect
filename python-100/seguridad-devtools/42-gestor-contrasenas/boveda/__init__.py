"""boveda: gestor de contraseñas local cifrado con una contraseña maestra."""
# API pública: primitivas de cifrado y el modelo de la bóveda.
from .cripto import ErrorDescifrado, cifrar, descifrar, derivar_clave
from .boveda import Boveda, Entrada

__all__ = ["ErrorDescifrado", "cifrar", "descifrar", "derivar_clave", "Boveda", "Entrada"]
