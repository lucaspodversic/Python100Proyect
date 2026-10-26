"""Resumen map-reduce con LLM y resumen extractivo de respaldo.

Map-reduce: si el texto no entra en un pedido, se divide en trozos, se
resume cada uno (map) y luego se resumen los resúmenes (reduce). Así se
pueden procesar artículos de cualquier largo con contexto acotado.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from resumen.extraccion import Articulo
from resumen.llm import ErrorLLM, Mensaje, ProveedorLLM

VACIAS = set("""a al ante con de del desde el en entre es esta este fue ha han la las lo los más mas
no o para pero por que se ser sin sobre su sus también un una uno y ya como son era muy""".split())


@dataclass
# VACIAS (arriba) son palabras sin contenido que no cuentan en la frecuencia.
class Resumen:
    titulo: str
    puntos: str
    metodo: str          # "llm" | "llm-mapreduce" | "extractivo"
    minutos_lectura: int
    trozos: int = 1


def _norm(p: str) -> str:
    p = unicodedata.normalize("NFKD", p.lower())
    return "".join(c for c in p if not unicodedata.combining(c))


def oraciones(texto: str) -> list[str]:
    # Corta después de . ! o ? seguido de espacio (lookbehind: el signo queda en
    # la oración). Se descartan las de 20 caracteres o menos (títulos, sueltos).
    return [o.strip() for o in re.split(r"(?<=[.!?])\s+", " ".join(texto.split())) if len(o.strip()) > 20]


def extractivo(texto: str, n: int = 3) -> str:
    """Elige las n oraciones con más palabras frecuentes (normalizado por largo)
    y las devuelve en el orden original del texto."""
    ors = oraciones(texto)
    palabras = [w for w in re.findall(r"\w+", _norm(texto)) if w not in VACIAS and len(w) > 2]
    freq = Counter(palabras)
    # Texto sin oraciones útiles: se devuelve el comienzo tal cual.
    if not ors or not freq:
        return texto[:300]
    maximo = max(freq.values())

    def puntaje(o: str) -> float:
        ws = [w for w in re.findall(r"\w+", _norm(o)) if w in freq]
        # Se divide por la raíz del largo (no por el largo) para favorecer un poco
        # las oraciones informativas largas sin que ganen solo por largas.
        return sum(freq[w] / maximo for w in ws) / (len(ws) ** 0.5 or 1)

    # Ordena índices por puntaje, toma los n mejores y los reordena por
    # posición: el resumen respeta el orden del texto original.
    elegidas = sorted(sorted(range(len(ors)), key=lambda i: -puntaje(ors[i]))[:n])
    return "\n".join(f"- {ors[i]}" for i in elegidas)


def trocear(texto: str, max_chars: int) -> list[str]:
    """Agrupa párrafos en trozos de hasta max_chars (sin cortar párrafos si se puede)."""
    trozos, actual = [], ""
    for p in texto.split("\n\n"):
        # +2 por el "\n\n" que los une. Un párrafo solo más largo que max_chars
        # forma su propio trozo (no se corta a la mitad).
        if actual and len(actual) + len(p) + 2 > max_chars:
            trozos.append(actual); actual = p
        else:
            actual = f"{actual}\n\n{p}" if actual else p
    if actual:
        trozos.append(actual)
    return trozos


def resumir(art: Articulo, llm: ProveedorLLM | None, max_chars: int = 6000, puntos: int = 5) -> Resumen:
    # Mínimo 1 minuto aunque el artículo sea muy corto.
    minutos = max(1, round(art.palabras / 200))   # ~200 palabras por minuto
    if not art.parrafos:
        raise ValueError("El artículo no tiene contenido extraíble")
    if llm is None:
        return Resumen(art.titulo, extractivo(art.texto), "extractivo", minutos)
    instruccion = f"Resumí en español en hasta {puntos} viñetas, sin inventar datos."
    trozos = trocear(art.texto, max_chars)
    try:
        # Entra en un solo pedido: no hace falta map-reduce.
        if len(trozos) == 1:
            r = llm.completar([Mensaje("system", instruccion), Mensaje("user", f"# {art.titulo}\n\n{trozos[0]}")])
            return Resumen(art.titulo, r.strip(), "llm", minutos)
        parciales = [llm.completar([Mensaje("system", "Resumí esta parte del artículo en 2-3 viñetas."),
                                    Mensaje("user", t)]).strip() for t in trozos]          # MAP
        final = llm.completar([Mensaje("system", instruccion + " Unificá y quitá repeticiones."),
                               Mensaje("user", "\n".join(parciales))])                       # REDUCE
        return Resumen(art.titulo, final.strip(), "llm-mapreduce", minutos, len(trozos))
    # Si el LLM falla en cualquier etapa, se cae al extractivo (sin red).
    except ErrorLLM:
        return Resumen(art.titulo, extractivo(art.texto), "extractivo", minutos, len(trozos))


def a_markdown(r: Resumen, art: Articulo, url: str) -> str:
    # Se omiten los datos vacíos para no dejar separadores colgando.
    meta = " · ".join(x for x in (art.autor, art.fecha, f"{r.minutos_lectura} min de lectura") if x)
    return f"# {r.titulo}\n\n_{meta}_  \nFuente: <{url}>\n\n{r.puntos}\n\n<sub>Método: {r.metodo}</sub>\n"
