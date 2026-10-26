"""Gráfico histórico + pronóstico con banda del 80 % (PNG, backend sin pantalla)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # sin display: funciona en servidores y en CI
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from .modelos import Pronostico  # noqa: E402


def graficar(serie: pd.Series, p: Pronostico, ruta: Path | str) -> Path:
    fig, ax = plt.subplots(figsize=(10, 4.5))
    # Histórico en gris oscuro, pronóstico en azul y banda del 80% semitransparente.
    ax.plot(serie.index, serie.values, label="Histórico", color="#37474f")
    ax.plot(p.media.index, p.media.values, label=f"Pronóstico ({p.modelo})", color="#1565c0")
    ax.fill_between(p.media.index, p.inferior.values, p.superior.values, alpha=0.25, color="#1565c0", label="Intervalo 80 %")
    ax.set_title("Ventas mensuales y pronóstico")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    ruta = Path(ruta)
    fig.savefig(ruta, dpi=110)
    # Cerrar la figura libera memoria (importante si se generan muchos gráficos en un proceso).
    plt.close(fig)
    return ruta
