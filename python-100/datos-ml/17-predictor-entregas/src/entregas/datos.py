"""Dataset sintético de pedidos de delivery.

La duración "real" sale de un proceso generador conocido, así los tests pueden
verificar que el modelo aprendió relaciones con sentido:

    duracion = preparacion
             + distancia / velocidad(vehiculo, clima)   # trayecto
             + congestion(hora, dia)                    # horas pico
             + 1.5 * pedidos_activos_del_repartidor     # cola
             + ruido log-normal (cola pesada, como en la realidad)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

COLUMNAS = ["distancia_km", "hora", "dia_semana", "clima", "vehiculo", "pedidos_activos", "preparacion_min"]
OBJETIVO = "duracion_min"

# Velocidad urbana promedio por vehículo; el clima la multiplica (tormenta = 55% de la normal).
VELOCIDAD_KMH = {"moto": 28.0, "auto": 22.0, "bici": 14.0}
FACTOR_CLIMA = {"despejado": 1.0, "nublado": 0.95, "lluvia": 0.75, "tormenta": 0.55}


def congestion(hora: np.ndarray, dia: np.ndarray) -> np.ndarray:
    """Minutos extra por tránsito: picos al mediodía y a la noche; menos el fin de semana."""
    # Dos campanas gaussianas: +6 min alrededor de las 13 y +9 min alrededor de las 20:30.
    # Fin de semana (dia ≥ 5) sólo el 60% de esa congestión.
    pico = 6 * np.exp(-((hora - 13) ** 2) / 2) + 9 * np.exp(-((hora - 20.5) ** 2) / 3)
    return pico * np.where(dia >= 5, 0.6, 1.0)


def generar_pedidos(n: int = 3000, semilla: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(semilla)
    df = pd.DataFrame({
        # Gamma(2, 1.6): media 3.2 km, muchos pedidos cercanos y pocos lejanos; recortado a 0.3-15 km.
        "distancia_km": np.round(rng.gamma(2.0, 1.6, n).clip(0.3, 15), 2),
        "hora": rng.choice(np.arange(10, 24), n, p=_pesos_hora()),
        "dia_semana": rng.integers(0, 7, n),  # 0 = lunes
        "clima": rng.choice(list(FACTOR_CLIMA), n, p=[0.55, 0.25, 0.15, 0.05]),
        "vehiculo": rng.choice(list(VELOCIDAD_KMH), n, p=[0.6, 0.15, 0.25]),
        # Pedidos que el repartidor ya lleva (Poisson de media 1.2); preparación ~ N(14, 4) entre 4 y 35 min.
        "pedidos_activos": rng.poisson(1.2, n),
        "preparacion_min": np.round(rng.normal(14, 4, n).clip(4, 35), 1),
    })
    vel = df["vehiculo"].map(VELOCIDAD_KMH) * df["clima"].map(FACTOR_CLIMA)
    # km / (km/h) = horas → × 60 = minutos.
    trayecto = df["distancia_km"] / vel * 60
    # Ruido asimétrico: rara vez baja de −3 min, pero a veces sube mucho (demoras imprevistas).
    ruido = rng.lognormal(0, 0.35, n) * 3 - 3
    df[OBJETIVO] = np.round(df["preparacion_min"] + trayecto + congestion(df["hora"].to_numpy(), df["dia_semana"].to_numpy())
                            + 1.5 * df["pedidos_activos"] + ruido, 1)
    return df


def _pesos_hora() -> np.ndarray:
    # Más pedidos al mediodía y a la cena; normalizados para que sumen 1 (exigido por rng.choice).
    w = np.array([1, 2, 6, 7, 4, 2, 2, 2, 3, 6, 9, 9, 6, 3], dtype=float)  # 10..23 hs
    return w / w.sum()
