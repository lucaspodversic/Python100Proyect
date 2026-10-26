"""Evaluación de respuestas: LLM con salida JSON validada + respaldo por palabras clave."""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field

from entrevistas.banco import Pregunta
from entrevistas.llm import ErrorLLM, Mensaje, ProveedorLLM

# Ojo: el prompt tiene llaves literales del JSON, por eso se completa con
# .replace("{claves}", ...) y no con .format() (que fallaría con esas llaves).
PROMPT = """Sos un entrevistador técnico. Evaluá la respuesta del candidato.
Devolvé SOLO JSON: {"puntaje": 1-10, "fortalezas": ["..."], "mejoras": ["..."],
"repregunta": "una pregunta de seguimiento o null"}
Puntos clave esperados (orientativos): {claves}"""


@dataclass
class Evaluacion:
    puntaje: int
    fortalezas: list[str] = field(default_factory=list)
    mejoras: list[str] = field(default_factory=list)
    repregunta: str | None = None
    origen: str = "llm"


# Minúsculas y sin tildes, para que "inmutable" y "Inmutable" coincidan.
def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def evaluar_por_claves(p: Pregunta, respuesta: str) -> Evaluacion:
    """Respaldo determinista: % de puntos clave mencionados -> puntaje 1..10."""
    r = _norm(respuesta)
    # Búsqueda por subcadena: simple y explicable. Efecto secundario conocido:
    # "inmutable" también cuenta como mención de "mutable".
    cubiertas = [c for c in p.claves if _norm(c) in r]
    faltan = [c for c in p.claves if c not in cubiertas]
    # Proporción de claves cubiertas escalada a 1..10 (nunca 0).
    puntaje = max(1, round(10 * len(cubiertas) / len(p.claves)))
    if len(respuesta.split()) < 8:  # respuestas muy cortas se penalizan
        puntaje = max(1, puntaje - 2)
    return Evaluacion(puntaje, [f"Mencionó: {c}" for c in cubiertas],
                      [f"Podría mencionar: {c}" for c in faltan], None, "claves")


def evaluar(p: Pregunta, respuesta: str, llm: ProveedorLLM) -> Evaluacion:
    if not respuesta.strip():
        return Evaluacion(1, [], ["No respondió"], None, "regla")
    try:
        salida = llm.completar([Mensaje("system", PROMPT.replace("{claves}", ", ".join(p.claves))),
                                Mensaje("user", f"Pregunta: {p.texto}\nRespuesta: {respuesta[:5000]}")])
        # Si no hay JSON, re.search da None y .group lanza AttributeError, que
        # está en la lista de excepciones capturadas => respaldo por claves.
        datos = json.loads(re.search(r"\{.*\}", salida, re.S).group(0))  # type: ignore[union-attr]
        puntaje = int(datos["puntaje"])
        # No se confía ciegamente en el LLM: un puntaje fuera de escala se descarta.
        if not 1 <= puntaje <= 10:
            raise ValueError("puntaje fuera de rango")
        rep = datos.get("repregunta")
        # Una repregunta vacía o que no sea string se trata como "sin repregunta".
        return Evaluacion(puntaje, list(datos.get("fortalezas", [])), list(datos.get("mejoras", [])),
                          rep if isinstance(rep, str) and rep.strip() else None)
    except (ErrorLLM, AttributeError, ValueError, KeyError, TypeError):
        return evaluar_por_claves(p, respuesta)
