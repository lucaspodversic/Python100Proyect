"""Tickets: carga desde CSV y generador sintético con asociaciones conocidas."""

from __future__ import annotations

import random
from pathlib import Path

import pandas as pd

CATALOGO = ["pan", "leche", "huevos", "manteca", "yerba", "azúcar", "fideos", "salsa de tomate", "queso rallado",
            "coca-cola", "fernet", "hielo", "cerveza", "papas fritas", "pañales", "toallitas", "café", "galletitas",
            "arroz", "aceite", "detergente", "esponja", "manzanas", "bananas"]

# Asociaciones "plantadas": (disparador, acompañantes, probabilidad de llevarlos juntos)
# El fernet con coca y hielo es la asociación más fuerte (80%), útil para verificar el algoritmo.
PATRONES = [
    ({"fernet"}, {"coca-cola", "hielo"}, 0.8),
    ({"fideos"}, {"salsa de tomate", "queso rallado"}, 0.6),
    ({"pañales"}, {"toallitas"}, 0.7),
    ({"yerba"}, {"azúcar"}, 0.5),
    ({"cerveza"}, {"papas fritas"}, 0.6),
    ({"detergente"}, {"esponja"}, 0.5),
]


def generar_tickets(n: int = 2000, semilla: int = 0) -> list[set[str]]:
    rng = random.Random(semilla)
    tickets = []
    for _ in range(n):
        # 1 a 4 productos al azar sin repetición: el "ruido" de fondo sin asociaciones.
        t = set(rng.sample(CATALOGO, rng.randint(1, 4)))  # compra base aleatoria
        for disparador, extra, p in PATRONES:
            # Si el ticket tiene el disparador, con probabilidad p se agregan sus acompañantes.
            if disparador <= t and rng.random() < p:
                t |= extra
        tickets.append(t)
    return tickets


def cargar_tickets(ruta: Path, col_ticket: str = "ticket", col_producto: str = "producto") -> list[set[str]]:
    """CSV en formato largo (una fila por producto vendido). Normaliza mayúsculas/espacios."""
    # dtype=str: los IDs de ticket "001" no se convierten a número; filas incompletas se descartan.
    df = pd.read_csv(ruta, dtype=str).dropna(subset=[col_ticket, col_producto])
    # " Pan " y "PAN" cuentan como el mismo producto.
    df[col_producto] = df[col_producto].str.strip().str.lower()
    # Un set por ticket: un producto repetido en el mismo ticket cuenta una sola vez.
    return [set(g) for _, g in df.groupby(col_ticket)[col_producto]]
