"""Banco de preguntas filtrable por rol y nivel ('*' = aplica a todos)."""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

RUTA_DEFECTO = Path(__file__).parent / "datos" / "preguntas.json"


@dataclass(frozen=True)
class Pregunta:
    id: str
    rol: str
    nivel: str
    competencia: str
    texto: str
    claves: tuple[str, ...]


def cargar_banco(ruta: str | Path = RUTA_DEFECTO) -> list[Pregunta]:
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    # JSON trae listas; se pasan a tupla para que la dataclass frozen sea hashable.
    return [Pregunta(**{**d, "claves": tuple(d["claves"])}) for d in datos]


def seleccionar(banco: list[Pregunta], rol: str, nivel: str, n: int, semilla: int | None = None) -> list[Pregunta]:
    """Elige n preguntas al azar (reproducible con semilla), intentando cubrir
    competencias distintas antes de repetir una."""
    # '*' = pregunta genérica (p. ej. comunicación) válida para cualquier rol/nivel.
    candidatas = [p for p in banco if p.rol in (rol, "*") and p.nivel in (nivel, "*")]
    # Se exige al menos una pregunta ESPECÍFICA del rol: con solo las genéricas ('*')
    # no sería una entrevista técnica para ese puesto.
    if not any(p.rol == rol for p in candidatas):
        raise ValueError(f"No hay preguntas para {rol}/{nivel}")
    # Generador propio (no el global de random): con la misma semilla se
    # obtiene la misma entrevista, útil para tests y para comparar candidatos.
    rng = random.Random(semilla)
    rng.shuffle(candidatas)
    elegidas, vistas = [], set()
    for p in candidatas:                     # primera pasada: una por competencia
        if p.competencia not in vistas:
            elegidas.append(p); vistas.add(p.competencia)
    # Si se piden más preguntas que competencias, se completan con las restantes
    # en el mismo orden mezclado.
    elegidas += [p for p in candidatas if p not in elegidas]   # luego el resto
    return elegidas[:n]
