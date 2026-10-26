"""Gráficos de resultados con matplotlib en modo **sin pantalla** (backend Agg).

``matplotlib.use("Agg")`` debe ejecutarse antes de importar ``pyplot`` para
que funcione en servidores sin entorno gráfico.
"""
from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402  (import tras elegir backend)


def grafico_barras(titulo: str, conteo: dict[str, int], promedio: float | None = None) -> bytes:
    """Devuelve un PNG con un gráfico de barras horizontal del conteo."""
    etiquetas = list(conteo)
    valores = list(conteo.values())
    fig, ax = plt.subplots(figsize=(6, 0.5 * len(etiquetas) + 1.5), dpi=100)
    try:
        barras = ax.barh(etiquetas, valores, color="#4C72B0")
        ax.invert_yaxis()  # primera opción arriba
        ax.bar_label(barras, padding=3)
        ax.set_xlabel("Respuestas")
        ax.set_title(titulo if promedio is None else f"{titulo} (promedio {promedio})", fontsize=10)
        ax.xaxis.get_major_locator().set_params(integer=True)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        return buf.getvalue()
    finally:
        plt.close(fig)  # libera memoria: importante en un servidor de larga vida
