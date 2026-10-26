"""Clasificación de sentimiento: LLM por lotes (JSON) + léxico de respaldo.

Por lotes porque mandar 20 textos en un solo pedido es mucho más barato y
rápido que 20 pedidos. Si el LLM falla o devuelve algo inválido para algún
id, ese texto se clasifica con el léxico.
"""
from __future__ import annotations

import json
import re
import unicodedata

from sentimiento.fuentes import Publicacion
from sentimiento.llm import ErrorLLM, Mensaje, ProveedorLLM

POSITIVAS = {"excelente", "genial", "bueno", "buena", "buenisimo", "encanta", "recomiendo", "rapido",
             "feliz", "mejor", "love", "great", "good", "amazing", "perfecto", "gracias"}
NEGATIVAS = {"malo", "mala", "pesimo", "horrible", "odio", "lento", "estafa", "caido", "falla", "error",
             "peor", "terrible", "bad", "hate", "worst", "nunca", "reclamo", "decepcion"}
# Las palabras van sin tildes porque _tokens normaliza el texto antes
# ("pésimo" => "pesimo", "decepción" => "decepcion").
NEGADORES = {"no", "ni", "sin", "not", "never"}
PROMPT = """Clasificá el sentimiento de cada publicación. Devolvé SOLO un JSON lista:
[{"id": "...", "sentimiento": "positivo|negativo|neutral", "score": -1.0 a 1.0}]"""
# Etiquetas válidas: cualquier otra que invente el LLM se descarta.
ETIQUETAS = {"positivo", "negativo", "neutral"}


def _tokens(t: str) -> list[str]:
    t = unicodedata.normalize("NFKD", t.lower())
    # Tras quitar tildes alcanza con [a-z]+; números y signos se ignoran.
    return re.findall(r"[a-z]+", "".join(c for c in t if not unicodedata.combining(c)))


def lexico(texto: str) -> tuple[str, float]:
    """Suma +1/-1 por palabra; un negador invierte la próxima palabra con carga
    dentro de las 2 siguientes ('no es bueno' -> negativo)."""
    puntos, n, alcance = 0, 0, 0   # alcance: cuántos tokens más afecta la negación
    for tk in _tokens(texto):
        if tk in NEGADORES:
            # El negador no suma: abre una "ventana" de 2 tokens donde la próxima
            # palabra con carga se invierte ("no es bueno": "es" consume 1, "bueno" -1).
            alcance = 2
            continue
        valor = 1 if tk in POSITIVAS else -1 if tk in NEGATIVAS else 0
        if valor:
            puntos += -valor if alcance else valor
            n += 1
            # La negación afecta solo a una palabra con carga.
            alcance = 0
        else:
            alcance = max(0, alcance - 1)
    # Promedio por palabra con carga (-1..1). Zona neutral entre -0,2 y 0,2
    # para no forzar polaridad con señales mixtas.
    score = round(puntos / n, 2) if n else 0.0
    return ("positivo" if score > 0.2 else "negativo" if score < -0.2 else "neutral"), score


def clasificar(pubs: list[Publicacion], llm: ProveedorLLM | None, lote: int = 20) -> dict[str, tuple[str, float]]:
    resultado: dict[str, tuple[str, float]] = {}
    for i in range(0, len(pubs), lote):
        # Lotes de `lote` textos (20 por defecto) para acotar el tamaño del prompt.
        grupo = pubs[i:i + lote]
        if llm is not None:
            # Cada texto se recorta a 500 caracteres; ~60 tokens de salida por ítem.
            entrada = json.dumps([{"id": p.id, "texto": p.texto[:500]} for p in grupo], ensure_ascii=False)
            try:
                salida = llm.completar([Mensaje("system", PROMPT), Mensaje("user", entrada)], max_tokens=60 * len(grupo))
                for d in json.loads(re.search(r"\[.*\]", salida, re.S).group(0)):  # type: ignore[union-attr]
                    # Solo se aceptan ids del lote (el LLM podría inventar otros) y el score
                    # se acota a [-1, 1] por si devuelve valores fuera de escala.
                    if d.get("sentimiento") in ETIQUETAS and d.get("id") in {p.id for p in grupo}:
                        resultado[d["id"]] = (d["sentimiento"], max(-1.0, min(1.0, float(d.get("score", 0)))))
            # Ante cualquier falla del lote, se sigue: el léxico cubre todo.
            except (ErrorLLM, AttributeError, ValueError, TypeError):
                pass
        for p in grupo:  # respaldo para lo que el LLM no resolvió
            resultado.setdefault(p.id, lexico(p.texto))
    return resultado
