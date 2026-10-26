"""Cálculo de RFM (Recency, Frequency, Monetary).

- **Recencia**: días desde la última compra hasta la fecha de referencia.
- **Frecuencia**: cantidad de compras (tickets distintos).
- **Monetario**: gasto total.
"""

from __future__ import annotations

import pandas as pd


def calcular_rfm(tx: pd.DataFrame, referencia: pd.Timestamp | str | None = None) -> pd.DataFrame:
    # Diferencia de conjuntos: columnas obligatorias ausentes → error claro.
    faltan = {"cliente", "fecha", "monto"} - set(tx.columns)
    if faltan:
        raise ValueError(f"Faltan columnas: {sorted(faltan)}")
    # assign devuelve una copia: no se modifica el DataFrame del llamador.
    tx = tx.assign(fecha=pd.to_datetime(tx["fecha"]))
    tx = tx[tx["monto"] > 0]  # devoluciones/anulaciones fuera
    # Sin referencia explícita se usa el día siguiente a la última compra del dataset,
    # así el cliente más reciente tiene recencia 1 y no 0.
    ref = pd.Timestamp(referencia) if referencia is not None else tx["fecha"].max() + pd.Timedelta(days=1)
    rfm = tx.groupby("cliente").agg(ultima=("fecha", "max"), frecuencia=("fecha", "size"), monetario=("monto", "sum"))
    # pop extrae la columna auxiliar "ultima" y la elimina del resultado.
    rfm["recencia"] = (ref - rfm.pop("ultima")).dt.days
    return rfm[["recencia", "frecuencia", "monetario"]]
