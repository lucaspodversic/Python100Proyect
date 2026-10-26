"""Motor: escaneo, movimiento seguro, vigilancia por sondeo y deshacer.

Decisiones de diseño:
- Sondeo (polling) con la librería estándar en lugar de `watchdog`
  para mantenerlo liviano y multiplataforma.
- "Estabilidad": sólo se mueve un archivo cuando su tamaño no cambió
  entre dos escaneos (evita mover descargas en curso sin extensión temporal).
- Nunca se sobrescribe: si el destino existe se agrega " (1)", " (2)"...
- Cada movimiento se registra en un JSON para poder deshacerlo.
"""
from __future__ import annotations

import json
import logging
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from .reglas import REGLAS_POR_DEFECTO, Regla, destino_para

# Logger propio: cada movimiento se informa con "nombre → destino".
log = logging.getLogger("organizador")


@dataclass(frozen=True)
# Rutas como str para serializarlas directo a JSON en el historial.
class Movimiento:
    origen: str
    destino: str


def ruta_libre(destino: Path) -> Path:
    """Si `destino` existe, devuelve 'nombre (n).ext' libre."""
    if not destino.exists():
        return destino
    # Se prueba " (1)", " (2)"... hasta encontrar un nombre libre (como hacen los navegadores).
    n = 1
    while True:
        cand = destino.with_name(f"{destino.stem} ({n}){destino.suffix}")
        if not cand.exists():
            return cand
        n += 1


@dataclass
class Organizador:
    carpeta: Path
    reglas: tuple[Regla, ...] = REGLAS_POR_DEFECTO
    por_defecto: str | None = "Otros"
    simulacion: bool = False
    registro: Path | None = None  # JSON con el historial para deshacer
    # Tamaño de cada archivo visto en la pasada anterior (para detectar estabilidad).
    _tamanos: dict[str, int] = field(default_factory=dict)

    def _carpetas_destino(self) -> set[str]:
        """Nombres de todas las carpetas a las que se puede mover algo."""
        return {r.carpeta for r in self.reglas} | ({self.por_defecto} if self.por_defecto else set())

    def candidatos(self) -> list[Path]:
        """Archivos sueltos en la raíz (no entra en subcarpetas)."""
        # Las subcarpetas (incluidas las de destino) nunca se recorren: no se re-mueve lo ya organizado.
        return sorted(p for p in self.carpeta.iterdir() if p.is_file())

    def organizar(self, exigir_estable: bool = False) -> list[Movimiento]:
        """Una pasada: mueve lo que corresponda y devuelve los movimientos."""
        movs: list[Movimiento] = []
        # Tamaños de esta pasada; reemplazan a los anteriores al final.
        vistos: dict[str, int] = {}
        for f in self.candidatos():
            if self.registro and f.resolve() == Path(self.registro).resolve():
                continue  # no movemos nuestro propio registro
            # None = no tocar (temporal de descarga, oculto, o sin regla y sin carpeta por defecto).
            carpeta = destino_para(f, self.reglas, self.por_defecto)
            if carpeta is None:
                continue
            tam = f.stat().st_size
            vistos[f.name] = tam
            # En vigilancia: si el tamaño cambió (o es la primera vez que se ve) se espera a la próxima pasada.
            if exigir_estable and self._tamanos.get(f.name) != tam:
                continue  # todavía puede estar escribiéndose
            # Nunca se pisa un archivo existente en el destino.
            destino = ruta_libre(self.carpeta / carpeta / f.name)
            # En simulación se calcula y se informa el destino, pero no se toca el disco.
            if not self.simulacion:
                destino.parent.mkdir(exist_ok=True)
                # shutil.move funciona también entre discos distintos (copia y borra si hace falta).
                shutil.move(str(f), str(destino))
            log.info("%s → %s", f.name, destino.relative_to(self.carpeta))
            movs.append(Movimiento(str(f), str(destino)))
        self._tamanos = vistos
        # Sólo se registran pasadas reales con al menos un movimiento.
        if movs and not self.simulacion:
            self._guardar_registro(movs)
        return movs

    def vigilar(self, intervalo: float = 5.0, iteraciones: int | None = None,
                dormir: Callable[[float], None] = time.sleep) -> int:
        """Bucle de vigilancia; devuelve el total de archivos movidos."""
        total, i = 0, 0
        # iteraciones=None → bucle infinito; los tests pasan un número y un `dormir` falso.
        while iteraciones is None or i < iteraciones:
            total += len(self.organizar(exigir_estable=True))
            i += 1
            dormir(intervalo)
        return total

    # ------- historial / deshacer -------
    def _guardar_registro(self, movs: list[Movimiento]) -> None:
        if not self.registro:
            return
        ruta = Path(self.registro)
        # Historial = lista de pasadas; cada pasada es la lista de movimientos que hizo.
        historial = json.loads(ruta.read_text()) if ruta.exists() else []
        historial.append([asdict(m) for m in movs])
        ruta.write_text(json.dumps(historial, ensure_ascii=False, indent=1))

    def deshacer(self) -> list[Movimiento]:
        """Revierte la última pasada registrada."""
        if not self.registro or not Path(self.registro).exists():
            return []
        historial = json.loads(Path(self.registro).read_text())
        # Caso borde: no hay pasadas que deshacer.
        if not historial:
            return []
        revertidos = []
        # Se saca la última pasada y se revierte en orden inverso al que se hizo.
        for m in reversed(historial.pop()):
            origen, destino = Path(m["origen"]), Path(m["destino"])
            # Si el usuario ya movió o borró el archivo, se omite sin fallar.
            if destino.exists():
                # Si en la ubicación original apareció otro archivo con el mismo nombre, no se lo pisa.
                final = ruta_libre(origen)
                shutil.move(str(destino), str(final))
                revertidos.append(Movimiento(str(destino), str(final)))
        # Se guarda el historial sin la pasada revertida (permite deshacer varias veces seguidas).
        Path(self.registro).write_text(json.dumps(historial, ensure_ascii=False, indent=1))
        return revertidos
