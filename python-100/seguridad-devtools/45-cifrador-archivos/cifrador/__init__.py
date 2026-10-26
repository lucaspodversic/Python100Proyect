"""cifrador: cifra archivos de cualquier tamaño con AES-256-GCM por bloques."""
# API pública: funciones sobre archivos en disco y sobre flujos binarios (BinaryIO).
from .nucleo import ErrorCifrado, cifrar_archivo, descifrar_archivo, cifrar_flujo, descifrar_flujo

__all__ = ["ErrorCifrado", "cifrar_archivo", "descifrar_archivo", "cifrar_flujo", "descifrar_flujo"]
