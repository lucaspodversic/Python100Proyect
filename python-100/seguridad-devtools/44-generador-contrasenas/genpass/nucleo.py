"""Generación de contraseñas.

Usamos `secrets.SystemRandom` (fuente criptográfica del sistema operativo),
NUNCA el módulo `random`, que es predecible.
"""
from __future__ import annotations

import math
import secrets
import string
from dataclasses import dataclass

AMBIGUOS = set("Il1O0o")  # caracteres que se confunden al leerlos
# Símbolos ASCII aceptados por la mayoría de los sitios (24 caracteres).
SIMBOLOS = "!@#$%^&*()-_=+[]{};:,.?/"
# Lista corta de palabras en español para frases de contraseña (diceware simplificado)
# Con 60 palabras cada una aporta log2(60) ≈ 5,9 bits; una lista diceware real tiene 7776 (≈12,9 bits).
PALABRAS = ("arbol barco cielo dedo estrella fuego gato hielo isla jardin kilo luna mar nube "
            "oso piedra queso rio sol tren uva viento yate zorro mate tango pampa lago monte "
            "rayo trigo lima cobre plata faro puente torre libro silla mesa perro nieve volcan "
            "brisa canela durazno eco flecha globo hoja iman jarra koala lapiz mango nido").split()


@dataclass
class Opciones:
    """Opciones configurables de generación."""

    largo: int = 16
    minusculas: bool = True
    mayusculas: bool = True
    digitos: bool = True
    simbolos: bool = True
    excluir_ambiguos: bool = False

    def clases(self) -> list[str]:
        """Devuelve la lista de conjuntos de caracteres habilitados."""
        # Cada clase es un string con sus caracteres; el orden es fijo y no afecta la aleatoriedad.
        clases = []
        if self.minusculas: clases.append(string.ascii_lowercase)
        if self.mayusculas: clases.append(string.ascii_uppercase)
        if self.digitos: clases.append(string.digits)
        if self.simbolos: clases.append(SIMBOLOS)
        # Se filtran los ambiguos de cada clase manteniendo la separación por clases.
        if self.excluir_ambiguos:
            clases = ["".join(c for c in cl if c not in AMBIGUOS) for cl in clases]
        # Se descartan clases que hayan quedado vacías tras el filtrado.
        return [c for c in clases if c]


def generar(op: Opciones | None = None) -> str:
    """Genera una contraseña que contiene al menos un carácter de cada clase."""
    op = op or Opciones()
    clases = op.clases()
    # Caso borde: todas las clases desactivadas → no hay alfabeto posible.
    if not clases:
        raise ValueError("Hay que habilitar al menos un tipo de carácter")
    # Caso borde: no entra al menos un carácter de cada clase obligatoria.
    if op.largo < len(clases):
        raise ValueError(f"El largo mínimo con estas opciones es {len(clases)}")
    # SystemRandom usa os.urandom: la mezcla también es criptográficamente segura.
    rnd = secrets.SystemRandom()
    # 1) Garantizamos un carácter de cada clase
    chars = [secrets.choice(c) for c in clases]
    # 2) Rellenamos con el alfabeto completo
    alfabeto = "".join(clases)
    chars += [secrets.choice(alfabeto) for _ in range(op.largo - len(chars))]
    # 3) Mezclamos para que las clases obligatorias no queden al principio
    rnd.shuffle(chars)
    return "".join(chars)


def generar_frase(palabras: int = 5, separador: str = "-", capitalizar: bool = False) -> str:
    """Genera una frase de contraseña tipo diceware."""
    # Caso borde: una frase vacía no protege nada.
    if palabras < 1:
        raise ValueError("Al menos una palabra")
    # Las palabras pueden repetirse: es lo que asume el cálculo de entropía (elecciones independientes).
    lista = [secrets.choice(PALABRAS) for _ in range(palabras)]
    if capitalizar:
        lista = [p.capitalize() for p in lista]
    return separador.join(lista)


def entropia_bits(largo: int, tam_alfabeto: int) -> float:
    """Entropía teórica = largo * log2(tamaño del alfabeto)."""
    # Caso borde: con un solo símbolo posible (o largo 0) no hay incertidumbre.
    if tam_alfabeto <= 1 or largo <= 0:
        return 0.0
    return largo * math.log2(tam_alfabeto)


def fortaleza(bits: float) -> str:
    """Clasificación orientativa según la entropía."""
    # Umbrales orientativos habituales: <40 se rompe por fuerza bruta offline con facilidad.
    if bits < 40: return "débil"
    if bits < 60: return "aceptable"
    if bits < 80: return "fuerte"
    return "muy fuerte"
