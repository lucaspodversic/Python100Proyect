"""Análisis y exportación: estadísticas, CSV y gráfico de barras ASCII."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from .api import DiaClima, Lugar


@dataclass(frozen=True)
class Estadisticas:
    """Resumen de un período. Los campos son None si no hubo ningún dato válido."""

    dias: int
    t_max_media: float | None
    t_min_media: float | None
    t_max_abs: tuple[float, str] | None   # (valor, fecha)
    t_min_abs: tuple[float, str] | None
    lluvia_total: float
    dias_lluvia: int                      # días con >= 1 mm (criterio meteorológico)


def estadisticas(dias: list[DiaClima]) -> Estadisticas:
    """Calcula medias, extremos y lluvia ignorando los valores faltantes (None)."""
    # Pares (valor, fecha): max()/min() sobre tuplas comparan primero el valor;
    # ante empate gana la fecha mayor/menor, lo cual es determinista.
    maxs = [(d.t_max, d.fecha.isoformat()) for d in dias if d.t_max is not None]
    mins = [(d.t_min, d.fecha.isoformat()) for d in dias if d.t_min is not None]
    lluvias = [d.lluvia_mm for d in dias if d.lluvia_mm is not None]
    r = lambda x: round(x, 1)   # 1 decimal: la precisión de los datos de origen
    return Estadisticas(len(dias), r(mean(v for v, _ in maxs)) if maxs else None,
                        r(mean(v for v, _ in mins)) if mins else None,
                        max(maxs) if maxs else None, min(mins) if mins else None,
                        # Una llovizna de 0,4 mm no cuenta como "día de lluvia" (umbral de 1 mm).
                        r(sum(lluvias)), sum(1 for l in lluvias if l >= 1))


def guardar_csv(lugar: Lugar, dias: list[DiaClima], ruta: Path) -> Path:
    """Escribe una fila por día; los None quedan como celdas vacías (csv convierte None en '')."""
    # newline="" es obligatorio con el módulo csv para no duplicar saltos en Windows.
    with Path(ruta).open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["lugar", "fecha", "t_max", "t_min", "lluvia_mm", "viento_max_kmh"])
        for d in dias:
            w.writerow([lugar.nombre, d.fecha.isoformat(), d.t_max, d.t_min, d.lluvia_mm, d.viento_max])
    return Path(ruta)


def grafico_ascii(dias: list[DiaClima], ancho: int = 30) -> str:
    """Barra por día desde la mínima a la máxima, en escala común."""
    # Sólo se grafican días con ambas temperaturas.
    validos = [d for d in dias if d.t_max is not None and d.t_min is not None]
    if not validos:
        return "(sin datos)"
    # Escala común a todo el período: así las barras se comparan entre sí.
    lo, hi = min(d.t_min for d in validos), max(d.t_max for d in validos)
    # Caso borde: todas las temperaturas iguales → hi == lo; se evita dividir por cero.
    escala = ancho / (hi - lo) if hi > lo else 1
    lineas = []
    for d in validos:
        # Columna de inicio (mínima) y de fin (máxima); al menos 1 bloque para que se vea la barra.
        ini, fin = int((d.t_min - lo) * escala), max(int((d.t_min - lo) * escala) + 1, int((d.t_max - lo) * escala))
        # Se marca la lluvia sólo si supera el umbral de "día de lluvia"; :g quita ceros sobrantes.
        lluvia = f" ☔{d.lluvia_mm:g}mm" if d.lluvia_mm and d.lluvia_mm >= 1 else ""
        # Relleno a la derecha para que la columna de la máxima quede alineada.
        lineas.append(f"{d.fecha:%d/%m} {d.t_min:5.1f} {' ' * ini}{'▇' * (fin - ini)}{' ' * (ancho - fin)} {d.t_max:5.1f}{lluvia}")
    return "\n".join(lineas)
