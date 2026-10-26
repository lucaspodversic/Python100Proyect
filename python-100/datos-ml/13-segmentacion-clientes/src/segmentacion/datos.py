"""Transacciones sintéticas con 4 perfiles latentes conocidos.

Conocer el perfil "verdadero" de cada cliente permite medir en los tests si el
clustering lo recupera (Adjusted Rand Index).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# perfil: (compras promedio en el año, ticket medio, días desde la última compra (media))
PERFILES = {
    "vip": (40, 250.0, 5),
    "frecuente": (25, 35.0, 10),
    "ocasional": (4, 80.0, 60),
    "perdido": (2, 60.0, 300),
}


def generar_transacciones(clientes_por_perfil: int = 60, semilla: int = 0,
                          fin: str = "2025-01-01") -> tuple[pd.DataFrame, pd.Series]:
    """Devuelve (transacciones[cliente, fecha, monto], perfil_real por cliente)."""
    # Generador con semilla: mismas transacciones en cada corrida.
    rng = np.random.default_rng(semilla)
    fin_ts = pd.Timestamp(fin)
    filas, perfiles = [], {}
    cid = 0
    for perfil, (compras, ticket, recencia) in PERFILES.items():
        for _ in range(clientes_por_perfil):
            cid += 1
            # Compras ~ Poisson(media del perfil), al menos 1 para que todo cliente tenga una transacción.
            n = max(1, rng.poisson(compras))
            # Días desde la última compra ~ exponencial con la media del perfil, tope 364 (dentro del año).
            ultima = int(min(364, rng.exponential(recencia)))
            # La primera fecha es la más reciente; el resto, anteriores dentro del año.
            dias = np.concatenate([[ultima], rng.integers(ultima, 365, n - 1)])
            # Lognormal: montos siempre positivos y asimétricos; mediana = ticket del perfil, dispersión ~30%.
            montos = rng.lognormal(np.log(ticket), 0.3, n).round(2)
            filas += [(f"C{cid:04d}", fin_ts - pd.Timedelta(days=int(d)), float(m)) for d, m in zip(dias, montos)]
            # Se guarda el perfil "verdadero" de cada cliente para poder medir el clustering en los tests.
            perfiles[f"C{cid:04d}"] = perfil
    return pd.DataFrame(filas, columns=["cliente", "fecha", "monto"]), pd.Series(perfiles, name="perfil")
