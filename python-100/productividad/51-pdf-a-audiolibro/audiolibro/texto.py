"""Extracción y preparación del texto.

gTTS (Google Translate TTS) acepta fragmentos cortos, así que dividimos
el texto en trozos respetando oraciones para que la voz no corte palabras.
"""
from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader


def extraer_texto(ruta_pdf: Path, desde: int = 1, hasta: int | None = None) -> list[str]:
    """Devuelve el texto de cada página (numeración desde 1, rango inclusivo)."""
    # pypdf lee el PDF localmente; no hace falta red.
    lector = PdfReader(str(ruta_pdf))
    # Caso borde: no se intenta adivinar contraseñas.
    if lector.is_encrypted:
        raise ValueError("El PDF está cifrado; descifralo primero")
    total = len(lector.pages)
    # Sin `hasta` (o mayor que el total) se recorta a la última página.
    hasta = min(hasta or total, total)
    # Caso borde: página inicial fuera del documento o rango invertido.
    if desde < 1 or desde > hasta:
        raise ValueError(f"Rango de páginas inválido (el PDF tiene {total})")
    # Índices 0-based internos; extract_text puede devolver None en páginas sin texto.
    return [lector.pages[i].extract_text() or "" for i in range(desde - 1, hasta)]


def limpiar_texto(texto: str) -> str:
    """Normaliza el texto para lectura en voz alta.

    - Une palabras cortadas con guion al final de línea ("compu-\\ntadora").
    - Convierte saltos de línea simples en espacios (los PDF cortan líneas).
    - Conserva los párrafos (doble salto) como pausa.
    - Colapsa espacios repetidos.
    """
    # Orden importante: primero unir guiones de corte, luego proteger párrafos, luego aplanar líneas.
    t = re.sub(r"(\w)-\n(\w)", r"\1\2", texto)
    t = re.sub(r"\n{2,}", "\u2029", t)  # marcador temporal de párrafo
    # Saltos simples (con espacios alrededor) → un espacio.
    t = re.sub(r"\s*\n\s*", " ", t)
    t = re.sub(r"[ \t]+", " ", t)
    return t.replace("\u2029", "\n\n").strip()


def trocear(texto: str, maximo: int = 500) -> list[str]:
    """Divide el texto en trozos <= `maximo` caracteres cortando en oraciones.

    Si una oración sola supera el máximo, se corta por palabras.
    """
    # Corte tras puntuación de fin de oración seguida de espacio, o en cada párrafo.
    oraciones = re.split(r"(?<=[.!?¡¿;:])\s+|\n\n", texto)
    trozos: list[str] = []
    actual = ""
    # `actual` acumula oraciones hasta que la siguiente ya no entra en el máximo.
    for o in (x.strip() for x in oraciones):
        if not o:
            continue
        while len(o) > maximo:  # oración gigante: cortar por el último espacio posible
            corte = o.rfind(" ", 0, maximo)
            # Caso borde: palabra sin espacios más larga que el máximo → corte duro.
            corte = corte if corte > 0 else maximo
            # Antes de partir la oración gigante se cierra el trozo en curso para mantener el orden.
            if actual:
                trozos.append(actual); actual = ""
            trozos.append(o[:corte].strip()); o = o[corte:].strip()
        # +1 por el espacio separador; si no entra, se cierra el trozo y la oración inicia uno nuevo.
        if len(actual) + len(o) + 1 > maximo and actual:
            trozos.append(actual); actual = o
        else:
            actual = f"{actual} {o}".strip()
    if actual:
        trozos.append(actual)
    return trozos
