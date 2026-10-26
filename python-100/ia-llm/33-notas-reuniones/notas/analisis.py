"""Extracción de resumen, decisiones y tareas (LLM + heurísticas de respaldo).

Estrategia: se le pide al LLM un JSON estricto. Si la salida no es JSON válido
o el LLM falla, se usan heurísticas con expresiones regulares, así la
herramienta SIEMPRE produce notas útiles.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field

from notas.llm import ErrorLLM, Mensaje, ProveedorLLM
from notas.transcripcion import Segmento

# Frases típicas de compromiso en español rioplatense ("me encargo de",
# "podés..."). Es una heurística: prioriza no perder tareas, aunque a veces
# capture alguna de más.
PATRONES_TAREA = re.compile(
    r"\b(voy a|me encargo de|me ocupo de|hay que|tenemos que|queda pendiente|te encargás de|podés)\b", re.I)
PATRONES_DECISION = re.compile(r"\b(decidimos|acordamos|quedamos en|se aprueba|vamos con)\b", re.I)
# Fechas relativas habituales en reuniones o dd/mm.
PATRON_FECHA = re.compile(
    r"\b(hoy|mañana|el (lunes|martes|miércoles|jueves|viernes)|esta semana|la semana que viene|\d{1,2}/\d{1,2})\b", re.I)

# Se pide JSON con forma fija para poder parsearlo sin ambigüedad.
PROMPT = """Analizá la transcripción de una reunión y devolvé SOLO un JSON con esta forma:
{"resumen": "2-3 oraciones", "decisiones": ["..."],
 "tareas": [{"responsable": "Nombre", "tarea": "...", "fecha": "... o null"}]}"""


@dataclass
class Tarea:
    responsable: str
    tarea: str
    fecha: str | None = None


@dataclass
class Notas:
    resumen: str
    decisiones: list[str]
    tareas: list[Tarea]
    participacion: dict[str, float] = field(default_factory=dict)   # % de tiempo hablado
    duracion: float = 0.0
    origen: str = "llm"   # "llm" o "heuristica"


def participacion(segmentos: list[Segmento]) -> dict[str, float]:
    """Porcentaje de tiempo de habla por persona."""
    tiempos: dict[str, float] = defaultdict(float)
    for s in segmentos:
        # max(0, ...) protege de segmentos con tiempos invertidos (errores del ASR).
        tiempos[s.hablante] += max(0.0, s.fin - s.inicio)
    # `or 1` evita dividir por cero si no hay segmentos.
    total = sum(tiempos.values()) or 1
    return {h: round(100 * t / total, 1) for h, t in sorted(tiempos.items(), key=lambda x: -x[1])}


def heuristicas(segmentos: list[Segmento]) -> tuple[list[str], list[Tarea]]:
    decisiones, tareas = [], []
    for s in segmentos:
        # Se analiza oración por oración: un segmento puede tener varias ideas.
        for oracion in re.split(r"(?<=[.!?])\s+", s.texto):
            if PATRONES_DECISION.search(oracion):
                decisiones.append(oracion.strip())
            # Una misma oración puede ser decisión y tarea a la vez (son dos if).
            if m := PATRONES_TAREA.search(oracion):
                fecha = PATRON_FECHA.search(oracion)
                # "Ana, podés ..." -> responsable Ana; si no, quien lo dijo
                vocativo = re.match(r"^([A-ZÁÉÍÓÚÑ]\w+),", oracion)
                # Solo con "podés"/"te encargás de" la tarea es del nombrado; con "voy a"
                # o "hay que" se asigna a quien habló.
                responsable = vocativo.group(1) if vocativo and m.group(1).lower() in ("podés", "te encargás de") else s.hablante
                tareas.append(Tarea(responsable, oracion.strip(), fecha.group(0) if fecha else None))
    return decisiones, tareas


def _json_de(texto: str) -> dict:
    """Extrae el primer objeto JSON del texto (los LLM a veces agregan ```json ...```)."""
    # Codicioso y con re.S (el punto incluye saltos de línea): toma desde la
    # primera "{" hasta la última "}", ignorando ```json y texto alrededor.
    m = re.search(r"\{.*\}", texto, re.S)
    if not m:
        raise ValueError("sin JSON")
    return json.loads(m.group(0))


def analizar(segmentos: list[Segmento], llm: ProveedorLLM) -> Notas:
    # Formato "[20s] Beto: ..." para que el LLM sepa quién dijo qué.
    transcripcion = "\n".join(f"[{s.inicio:.0f}s] {s.hablante}: {s.texto}" for s in segmentos)
    duracion = max((s.fin for s in segmentos), default=0.0)
    base = dict(participacion=participacion(segmentos), duracion=duracion)
    try:
        # Se recorta a 60.000 caracteres (~15k tokens) para no exceder el contexto.
        datos = _json_de(llm.completar([Mensaje("system", PROMPT), Mensaje("user", transcripcion[:60_000])],
                                       max_tokens=1200))
        tareas = [Tarea(t.get("responsable") or "?", t["tarea"], t.get("fecha")) for t in datos.get("tareas", [])]
        return Notas(str(datos["resumen"]), [str(d) for d in datos.get("decisiones", [])], tareas, **base)
    # ValueError incluye json.JSONDecodeError. KeyError/TypeError: JSON con
    # otra forma (falta "resumen", "tareas" no es lista...). En todos los
    # casos se cae a las heurísticas.
    except (ErrorLLM, ValueError, KeyError, TypeError):
        decisiones, tareas = heuristicas(segmentos)
        primeras = " ".join(s.texto for s in segmentos[:2])
        return Notas(f"Reunión de {duracion / 60:.0f} min. Inicio: {primeras[:200]}",
                     decisiones, tareas, origen="heuristica", **base)


def a_markdown(n: Notas, titulo: str = "Notas de reunión") -> str:
    """Genera el documento final en Markdown."""
    lineas = [f"# {titulo}", "", f"*Duración:* {n.duracion / 60:.1f} min · *Generado por:* {n.origen}", "",
              "## Resumen", n.resumen, "", "## Decisiones"]
    # Lista vacía es falsa => se muestra "(ninguna)" en vez de una sección vacía.
    lineas += [f"- {d}" for d in n.decisiones] or ["- (ninguna)"]
    lineas += ["", "## Tareas", "| Responsable | Tarea | Fecha |", "|---|---|---|"]
    # Un "|" dentro del texto rompería la tabla Markdown: se reemplaza.
    lineas += [f"| {t.responsable} | {t.tarea.replace('|', '/')} | {t.fecha or '-'} |" for t in n.tareas]
    lineas += ["", "## Participación"] + [f"- {h}: {p}%" for h, p in n.participacion.items()]
    return "\n".join(lineas) + "\n"
