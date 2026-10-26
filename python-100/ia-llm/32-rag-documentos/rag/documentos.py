"""Carga de documentos y división en fragmentos ("chunks").

Por qué fragmentar: los LLM tienen contexto limitado y la búsqueda es más
precisa sobre trozos chicos. Se corta por párrafos y, si un párrafo es muy
largo, por oraciones; se agrega un solapamiento para no perder contexto en
los bordes entre fragmentos.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Fragmento:
    id: str          # "archivo.md#3"
    fuente: str      # nombre del archivo
    texto: str


def cargar_texto(ruta: Path) -> str:
    """Lee .txt/.md directo; .pdf requiere `pypdf` (dependencia opcional)."""
    if ruta.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader  # import perezoso: solo si hay PDFs
        except ImportError as e:  # pragma: no cover - depende del entorno
            raise RuntimeError("Instalá el extra: pip install -e '.[pdf]'") from e
        # Una página por párrafo; `or ""` cubre páginas escaneadas sin texto.
        return "\n\n".join(p.extract_text() or "" for p in PdfReader(str(ruta)).pages)
    # errors="replace": un byte inválido no frena toda la indexación.
    return ruta.read_text(encoding="utf-8", errors="replace")


def fragmentar(texto: str, fuente: str, max_chars: int = 600, solape: int = 100) -> list[Fragmento]:
    """Divide el texto en fragmentos de hasta ~max_chars con solapamiento."""
    # Con solape >= tamaño el corte duro de abajo no avanzaría (bucle infinito).
    if solape >= max_chars:
        raise ValueError("El solapamiento debe ser menor que el tamaño")
    # 1) unidades: párrafos; los largos se parten en oraciones
    unidades: list[str] = []
    for parrafo in re.split(r"\n\s*\n", texto):
        # Colapsa saltos de línea y espacios múltiples dentro del párrafo.
        parrafo = " ".join(parrafo.split())
        if not parrafo:
            continue
        if len(parrafo) <= max_chars:
            unidades.append(parrafo)
        else:
            # Lookbehind: corta DESPUÉS del signo, así cada oración conserva su punto.
            unidades.extend(o for o in re.split(r"(?<=[.!?])\s+", parrafo) if o)
    # 2) agrupar unidades hasta llenar el tamaño
    trozos: list[str] = []
    actual = ""
    for u in unidades:
        while len(u) > max_chars:  # oración gigante: corte duro
            # Cada pedazo arranca `solape` caracteres antes del fin del anterior;
            # avanza max_chars - solape > 0 por vuelta, así que siempre termina.
            trozos.append(u[:max_chars]); u = u[max_chars - solape:]
        # El +1 es el espacio que uniría `actual` y `u`.
        if actual and len(actual) + 1 + len(u) > max_chars:
            trozos.append(actual)
            cola = actual[-solape:] if solape else ""
            # el solape empieza en un límite de palabra
            # Se descarta la primera palabra (posiblemente cortada) de la cola. Por
            # eso un fragmento puede medir hasta max_chars + solape.
            actual = (cola.split(" ", 1)[-1] + " " + u).strip() if cola else u
        else:
            actual = f"{actual} {u}".strip()
    if actual:
        trozos.append(actual)
    # id estable "archivo#n": sirve para citar y para comparar resultados.
    return [Fragmento(f"{fuente}#{i}", fuente, t) for i, t in enumerate(trozos)]


def cargar_carpeta(carpeta: str | Path, **kw) -> list[Fragmento]:
    """Carga y fragmenta todos los .txt/.md/.pdf de una carpeta (recursivo)."""
    frags: list[Fragmento] = []
    # sorted: orden determinista de archivos => mismos ids en cada indexación.
    for ruta in sorted(Path(carpeta).rglob("*")):
        if ruta.suffix.lower() in {".txt", ".md", ".pdf"} and ruta.is_file():
            frags.extend(fragmentar(cargar_texto(ruta), ruta.name, **kw))
    return frags
