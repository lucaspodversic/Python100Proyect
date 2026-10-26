"""Banco de palabras por categoría y dibujos ASCII (7 etapas)."""

# Palabras con tildes, diéresis y ñ a propósito, para ejercitar la normalización.
PALABRAS: dict[str, list[str]] = {
    "animales": ["murciélago", "pingüino", "elefante", "jirafa", "ñandú", "cocodrilo"],
    "frutas": ["frutilla", "mandarina", "ananá", "durazno", "pomelo"],
    "programación": ["variable", "función", "diccionario", "recursión", "excepción"],
}

# Etapa 0 = horca vacía; cada fallo agrega una parte: cabeza, torso, brazos y piernas.
ETAPAS: list[str] = [
    "  +---+\n      |\n      |\n      |\n     ===",
    "  +---+\n  O   |\n      |\n      |\n     ===",
    "  +---+\n  O   |\n  |   |\n      |\n     ===",
    "  +---+\n  O   |\n /|   |\n      |\n     ===",
    "  +---+\n  O   |\n /|\\  |\n      |\n     ===",
    "  +---+\n  O   |\n /|\\  |\n /    |\n     ===",
    "  +---+\n  O   |\n /|\\  |\n / \\  |\n     ===",
]
