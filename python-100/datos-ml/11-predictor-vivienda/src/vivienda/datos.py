"""Dataset sintético reproducible.

En un caso real se usaría un CSV de avisos inmobiliarios (p. ej. Properati o el
clásico *California Housing* de sklearn). Acá generamos datos con una fórmula
conocida + ruido, lo que permite verificar en los tests que el modelo aprende
las relaciones correctas (más m² => más caro, más antigüedad => más barato).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Precio base por m² (USD) de cada barrio ficticio.
BARRIOS: dict[str, float] = {"Centro": 2600, "Norte": 3200, "Sur": 1500, "Oeste": 1900, "Costa": 3800}
# Separar numéricas y categóricas permite preprocesarlas distinto (escalado vs one-hot).
NUMERICAS = ["m2", "ambientes", "banos", "antiguedad", "cochera", "distancia_subte_km"]
CATEGORICAS = ["barrio"]
COLUMNAS = NUMERICAS + CATEGORICAS
OBJETIVO = "precio"


def generar_dataset(n: int = 1000, semilla: int = 42) -> pd.DataFrame:
    # Generator moderno de NumPy con semilla: mismo dataset en cada llamada con la misma semilla.
    rng = np.random.default_rng(semilla)
    barrio = rng.choice(list(BARRIOS), size=n)
    # Gamma(6, 12): media 72 m², asimétrica a la derecha como la oferta real; recortada a 25-400 m².
    m2 = rng.gamma(shape=6, scale=12, size=n).clip(25, 400).round()
    # ~1 ambiente cada 25 m² ± 1, entre 1 y 8; baños ~ ambientes / 2.5 (+0/+1), entre 1 y 4.
    ambientes = np.clip((m2 / 25).round() + rng.integers(-1, 2, n), 1, 8).astype(int)
    banos = np.clip((ambientes / 2.5).round() + rng.integers(0, 2, n), 1, 4).astype(int)
    # Antigüedad 0-79 años; cochera con probabilidad 35%; distancia al subte exponencial (media 1.2 km).
    antiguedad = rng.integers(0, 80, n)
    cochera = rng.binomial(1, 0.35, n)
    dist = rng.exponential(1.2, n).round(2)
    base = np.array([BARRIOS[b] for b in barrio])
    # Fórmula "verdad": precio/m² del barrio × m², −0.4% por año de antigüedad, −4% por km al subte
    # (tope 5 km → máx. −20%), +9000 por baño y +15000 por cochera.
    precio = (base * m2 * (1 - 0.004 * antiguedad) * (1 - 0.04 * np.minimum(dist, 5))
              + 9000 * banos + 15000 * cochera)
    precio *= rng.normal(1, 0.07, n)  # ruido multiplicativo del ~7 %
    return pd.DataFrame({"m2": m2, "ambientes": ambientes, "banos": banos, "antiguedad": antiguedad,
                         "cochera": cochera, "distancia_subte_km": dist, "barrio": barrio,
                         # round(-2) redondea a centenas de dólares, como un precio publicado.
                         OBJETIVO: precio.round(-2)})
