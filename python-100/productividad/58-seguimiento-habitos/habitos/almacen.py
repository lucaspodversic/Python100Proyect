"""Persistencia en un JSON legible (fechas ISO), con escritura atómica."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from pathlib import Path

from .modelo import Habito


class Almacen:
    """Lee y escribe todos los hábitos en un único archivo JSON."""
    def __init__(self, ruta: Path) -> None:
        self.ruta = Path(ruta)

    def cargar(self) -> dict[str, Habito]:
        # Primera ejecución: todavía no hay archivo.
        if not self.ruta.exists():
            return {}
        datos = json.loads(self.ruta.read_text(encoding="utf-8"))
        # Se reconstruyen tipos: fechas ISO → date, lista de días → frozenset, hechos → set de date.
        return {n: Habito(n, date.fromisoformat(d["creado"]), frozenset(d["dias_semana"]),
                          {date.fromisoformat(x) for x in d["hechos"]}) for n, d in datos.items()}

    def guardar(self, habitos: dict[str, Habito]) -> None:
        # Listas ordenadas: el JSON queda estable (útil para diffs o control de versiones).
        datos = {n: {"creado": h.creado.isoformat(), "dias_semana": sorted(h.dias_semana),
                     "hechos": sorted(x.isoformat() for x in h.hechos)} for n, h in habitos.items()}
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        # Escribimos en un temporal y renombramos: nunca queda un JSON a medias
        # En la misma carpeta que el destino: os.replace sólo es atómico dentro del mismo sistema de archivos.
        fd, tmp = tempfile.mkstemp(dir=self.ruta.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
        # Reemplazo atómico (también en Windows, a diferencia de os.rename sobre un archivo existente).
        os.replace(tmp, self.ruta)
