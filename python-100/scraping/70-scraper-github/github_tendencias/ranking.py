"""Ranking por ritmo de estrellas y salidas en Markdown / CSV."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from .api import Repo


def ordenar_por_ritmo(repos: list[Repo], ahora: datetime) -> list[Repo]:
    """Ordena por estrellas/día (desempata por estrellas totales)."""
    # Un repo nuevo con 500 estrellas en un día supera a uno de una semana con 900.
    return sorted(repos, key=lambda r: (r.estrellas_por_dia(ahora), r.estrellas), reverse=True)


def _md(t: str) -> str:
    """Escapa '|' y saltos para no romper la tabla Markdown."""
    # split()/join también colapsa espacios múltiples y saltos de línea en uno.
    return " ".join(t.replace("|", "\\|").split())


def markdown(repos: list[Repo], ahora: datetime, max_desc: int = 80) -> str:
    """Tabla Markdown numerada; descripciones largas se recortan con '…'."""
    filas = ["| # | Repositorio | Lenguaje | ⭐ | ⭐/día | Descripción |", "|---|---|---|---|---|---|"]
    for n, r in enumerate(repos, 1):
        # Se recorta ANTES de escapar: el largo cuenta caracteres visibles.
        d = r.descripcion if len(r.descripcion) <= max_desc else r.descripcion[: max_desc - 1] + "…"
        # El nombre se enlaza a la página del repo. Las URLs de GitHub no contienen '|' ni ')'.
        filas.append(f"| {n} | [{_md(r.nombre)}]({r.url}) | {_md(r.lenguaje)} | {r.estrellas} | "
                     f"{r.estrellas_por_dia(ahora)} | {_md(d)} |")
    return "\n".join(filas)


def exportar_csv(repos: list[Repo], ruta: Path, ahora: datetime) -> Path:
    """Un repo por fila; los temas se unen con ';' para caber en una celda."""
    # newline="" es obligatorio con csv; utf-8 por descripciones con emojis o tildes.
    with Path(ruta).open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["nombre", "url", "lenguaje", "estrellas", "forks", "estrellas_por_dia", "creado", "temas"])
        for r in repos:
            w.writerow([r.nombre, r.url, r.lenguaje, r.estrellas, r.forks, r.estrellas_por_dia(ahora),
                        r.creado.isoformat(), ";".join(r.temas)])
    return Path(ruta)
