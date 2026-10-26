"""Gráficos con matplotlib en modo sin pantalla (backend Agg) a PNG."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # imprescindible en servidores/cron sin entorno gráfico
import matplotlib.pyplot as plt  # noqa: E402


def grafico_linea(serie: list[tuple[str, float]], titulo: str, destino: Path) -> Path:
    """Línea de evolución (ej. facturación mensual)."""
    # 7×3 pulgadas a 100 dpi = 700×300 px: proporción apaisada que entra a 180 mm de ancho en A4.
    fig, ax = plt.subplots(figsize=(7, 3), dpi=100)
    etiquetas = [s[0] for s in serie]
    ax.plot(etiquetas, [s[1] for s in serie], marker="o", color="#305496")
    ax.set_title(titulo)
    ax.grid(alpha=0.3)
    # Etiquetas "2024-01"... rotadas para que no se superpongan con 12 meses.
    ax.tick_params(axis="x", rotation=45)
    # tight_layout ajusta márgenes para que título y etiquetas rotadas no queden cortados.
    fig.tight_layout()
    fig.savefig(destino)
    plt.close(fig)  # liberar memoria: importante en procesos programados
    return destino


def grafico_barras(serie: list[tuple[str, float]], titulo: str, destino: Path) -> Path:
    """Barras horizontales (ej. facturación por región)."""
    fig, ax = plt.subplots(figsize=(7, 3), dpi=100)
    # Barras horizontales: los nombres de región se leen sin rotar.
    ax.barh([s[0] for s in serie], [s[1] for s in serie], color="#70AD47")
    # barh dibuja el primer elemento abajo; invertimos para que el mayor (primero) quede arriba.
    ax.invert_yaxis()
    ax.set_title(titulo)
    fig.tight_layout()
    fig.savefig(destino)
    plt.close(fig)
    return destino
