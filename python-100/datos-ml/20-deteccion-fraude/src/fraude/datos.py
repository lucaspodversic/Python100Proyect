"""Transacciones sintéticas con ~1 % de fraude.

Patrones plantados (inspirados en fraude con tarjeta real):
- montos más altos y "redondos";
- madrugada (0-5 hs);
- muchas transacciones en la última hora (*card testing*);
- lejos del domicilio / país distinto / dispositivo nuevo;
- online y rubros de alto riesgo (electrónica, cripto, gift cards).

Hay solapamiento a propósito: muchas compras legítimas también son online o
nocturnas, así que el problema no es trivialmente separable.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RUBROS = ["supermercado", "restaurante", "combustible", "ropa", "electronica", "viajes", "cripto", "gift_cards"]
# Referencia de riesgo relativo por rubro (documental); la señal real está en las probabilidades de abajo.
RIESGO_RUBRO = {"electronica": 1.2, "cripto": 2.0, "gift_cards": 2.2, "viajes": 0.6}
NUMERICOS = ["monto", "hora", "distancia_km", "tx_ultima_hora", "ratio_monto_promedio", "antiguedad_cuenta_dias"]
BINARIOS = ["online", "pais_distinto", "dispositivo_nuevo", "monto_redondo"]
ATRIBUTOS = NUMERICOS + BINARIOS + ["rubro"]


def generar_transacciones(n: int = 20000, tasa_fraude: float = 0.01, semilla: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(semilla)
    # Cada transacción es fraude con probabilidad tasa_fraude (1% → ~300 en 30.000).
    fraude = rng.random(n) < tasa_fraude
    nf = int(fraude.sum())

    # Toma el valor legítimo y lo reemplaza por el de la distribución de fraude en las filas fraudulentas.
    def mezcla(legit: np.ndarray, fraud: np.ndarray) -> np.ndarray:
        out = legit.copy()
        out[fraude] = fraud
        return out

    # Lognormal: mediana legítima e^3.6 ≈ $37; fraude e^4.1 ≈ $60 y con más dispersión.
    monto = mezcla(rng.lognormal(3.6, 0.9, n), rng.lognormal(4.1, 1.1, nf))
    # 20% de montos redondos en fraude vs. 8% legítimo; se redondean a decenas (mínimo $10).
    redondo = rng.random(n) < np.where(fraude, 0.2, 0.08)
    monto = np.where(redondo, np.round(monto, -1).clip(10), np.round(monto, 2))
    hora = mezcla(rng.choice(24, n, p=_perfil_horario()), rng.choice(24, nf, p=_perfil_horario(fraude=True)))
    # Las probabilidades siguen el orden de RUBROS: el fraude se concentra en electrónica, cripto y gift cards.
    rubro = mezcla(rng.choice(RUBROS, n, p=[0.3, 0.2, 0.15, 0.13, 0.1, 0.07, 0.03, 0.02]),
                   rng.choice(RUBROS, nf, p=[0.15, 0.1, 0.1, 0.12, 0.25, 0.1, 0.08, 0.1]))
    df = pd.DataFrame({
        "monto": monto,
        "hora": hora,
        # Distancia media al domicilio: 8 km legítimas vs. 40 km fraude.
        "distancia_km": np.round(mezcla(rng.exponential(8, n), rng.exponential(40, nf)), 1),
        # Card testing: más transacciones recientes (media 1.0 vs. 0.4).
        "tx_ultima_hora": mezcla(rng.poisson(0.4, n), rng.poisson(1.0, nf)),
        "ratio_monto_promedio": np.round(mezcla(rng.lognormal(0, 0.5, n), rng.lognormal(0.5, 0.7, nf)), 3),
        # Cuentas fraudulentas tienden a ser más nuevas (incluso de 1 día).
        "antiguedad_cuenta_dias": mezcla(rng.integers(30, 3000, n), rng.integers(1, 2000, nf)),
        # Binarios con probabilidades distintas por clase pero solapadas (no separables de forma trivial).
        "online": (rng.random(n) < np.where(fraude, 0.6, 0.35)).astype(int),
        "pais_distinto": (rng.random(n) < np.where(fraude, 0.12, 0.03)).astype(int),
        "dispositivo_nuevo": (rng.random(n) < np.where(fraude, 0.3, 0.08)).astype(int),
        "monto_redondo": redondo.astype(int),
        "rubro": rubro,
        "fraude": fraude.astype(int),
    })
    return df


def _perfil_horario(fraude: bool = False) -> np.ndarray:
    # Peso relativo por hora 0-23: poca actividad de madrugada, pico por la tarde-noche.
    base = np.array([1, 0.6, 0.4, 0.3, 0.3, 0.5, 1, 2, 3, 4, 5, 5, 6, 6, 5, 5, 5, 6, 7, 7, 6, 4, 3, 2], dtype=float)
    if fraude:
        base[:6] *= 3  # madrugada mucho más frecuente
    # Normalizado para que sume 1 (requisito de rng.choice con p=...).
    return base / base.sum()
