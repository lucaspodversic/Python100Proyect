"""venvctl: gestor centralizado de entornos virtuales de Python."""
# API pública: el gestor, su modelo de información y su excepción.
from .gestor import Gestor, InfoEntorno, ErrorGestor

__all__ = ["Gestor", "InfoEntorno", "ErrorGestor"]
