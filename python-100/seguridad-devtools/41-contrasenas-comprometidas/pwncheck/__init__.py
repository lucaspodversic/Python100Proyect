"""pwncheck: comprueba si una contraseña aparece en filtraciones conocidas.

Usa la API "Pwned Passwords" de Have I Been Pwned con el modelo
k-anonymity: sólo se envían los primeros 5 caracteres del hash SHA-1,
nunca la contraseña ni el hash completo.
"""
# API pública: el modelo de resultado, los pasos del hash y la función principal.
from .nucleo import ResultadoChequeo, dividir_hash, sha1_mayusculas, comprobar

__all__ = ["ResultadoChequeo", "dividir_hash", "sha1_mayusculas", "comprobar"]
