"""Lectura de métricas del sistema con la librería estándar (sin psutil).

En Linux la CPU se calcula con dos lecturas de /proc/stat y la memoria
con /proc/meminfo. Las rutas son configurables para testear con fixtures.
"""
from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Metricas:
    """Porcentajes de uso (0-100)."""

    cpu: float
    memoria: float
    disco: float


# Interfaz estructural: cualquier objeto con leer() -> Metricas sirve (los tests usan proveedores fijos).
class ProveedorMetricas(Protocol):
    def leer(self) -> Metricas: ...


def _tiempos_cpu(texto: str) -> tuple[int, int]:
    """Devuelve (inactivo, total) a partir de la línea 'cpu' de /proc/stat."""
    # Primera línea de /proc/stat: "cpu user nice system idle iowait irq softirq steal ...", en ticks acumulados.
    campos = [int(x) for x in texto.splitlines()[0].split()[1:]]
    inactivo = campos[3] + (campos[4] if len(campos) > 4 else 0)  # idle + iowait
    # El total incluye todos los estados; ocupado = total - inactivo.
    return inactivo, sum(campos)


def uso_cpu(antes: str, despues: str) -> float:
    """% de CPU ocupada entre dos instantáneas de /proc/stat."""
    i1, t1 = _tiempos_cpu(antes)
    i2, t2 = _tiempos_cpu(despues)
    # Los contadores son acumulados desde el arranque: el uso real sale de la diferencia entre dos lecturas.
    delta = t2 - t1
    # Caso borde: sin ticks transcurridos (lecturas idénticas) no hay división por cero.
    return 0.0 if delta <= 0 else round(100.0 * (1 - (i2 - i1) / delta), 1)


def uso_memoria(meminfo: str) -> float:
    """% de memoria usada = 1 - MemAvailable / MemTotal."""
    vals = {}
    # Formato "Clave:   valor kB"; se toma el número (en kB) y se ignora la unidad.
    for linea in meminfo.splitlines():
        clave, _, resto = linea.partition(":")
        if resto.strip():
            vals[clave] = int(resto.split()[0])
    total = vals.get("MemTotal", 0)
    # MemAvailable incluye cachés liberables (más realista); en kernels viejos sin ese campo se usa MemFree.
    disponible = vals.get("MemAvailable", vals.get("MemFree", 0))
    # Caso borde: texto vacío o sin MemTotal → 0 en vez de división por cero.
    return 0.0 if not total else round(100.0 * (1 - disponible / total), 1)


class ProveedorLinux:
    """Proveedor real para Linux."""

    # raiz_proc configurable: los tests apuntan a una carpeta de fixtures con stat y meminfo.
    def __init__(self, raiz_proc: Path = Path("/proc"), punto_montaje: str = "/", intervalo: float = 0.5):
        self.proc = Path(raiz_proc)
        self.montaje = punto_montaje
        self.intervalo = intervalo

    def leer(self) -> Metricas:
        antes = (self.proc / "stat").read_text()
        time.sleep(self.intervalo)  # ventana de medición de CPU
        despues = (self.proc / "stat").read_text()
        # Uso del sistema de archivos donde está el punto de montaje (por defecto la raíz).
        disco = shutil.disk_usage(self.montaje)
        return Metricas(cpu=uso_cpu(antes, despues),
                        memoria=uso_memoria((self.proc / "meminfo").read_text()),
                        disco=round(100.0 * disco.used / disco.total, 1))
