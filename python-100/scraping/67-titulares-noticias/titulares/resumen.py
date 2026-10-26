"""Agregación: deduplicar, filtrar por palabras clave, ordenar y formatear."""
from __future__ import annotations

import unicodedata
from datetime import datetime, timedelta
from html import escape
from typing import Iterable

from .feeds import Noticia


def _norm(t: str) -> str:
    """Minúsculas sin tildes, para comparar títulos y palabras clave."""
    # NFD separa "é" en "e" + acento combinante (categoría Mn), que luego se descarta.
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def agregar(listas: Iterable[list[Noticia]], limite: int | None = None) -> list[Noticia]:
    """Une feeds, quita duplicados (mismo enlace o mismo título) y ordena de más nueva a más vieja."""
    vistos_e, vistos_t, salida = set(), set(), []
    for lista in listas:
        for n in lista:
            # Título normalizado: "AVANCES EN ENERGÍA" y "Avances en energía" son el mismo titular
            # aunque vengan de medios distintos (agencias que se replican).
            t = " ".join(_norm(n.titulo).split())
            if n.enlace in vistos_e or t in vistos_t:
                continue    # se conserva la primera aparición (orden de los feeds = prioridad)
            vistos_e.add(n.enlace); vistos_t.add(t); salida.append(n)
    # Las noticias sin fecha van al final (-inf); sort es estable, así que mantienen su orden relativo.
    salida.sort(key=lambda n: n.fecha.timestamp() if n.fecha else float("-inf"), reverse=True)
    return salida[:limite] if limite else salida


def filtrar(noticias: list[Noticia], incluir: list[str] = (), excluir: list[str] = (),
            desde: datetime | None = None) -> list[Noticia]:
    """Filtra por palabras clave (en título o resumen, sin tildes/mayúsculas) y antigüedad.

    incluir: al menos una debe aparecer (vacío = no filtra). excluir: ninguna debe aparecer.
    desde: descarta noticias más viejas; las que no tienen fecha también se descartan
    (no se puede saber si son recientes).
    """
    inc, exc = [_norm(p) for p in incluir], [_norm(p) for p in excluir]
    def ok(n: Noticia) -> bool:
        t = _norm(f"{n.titulo} {n.resumen}")
        return ((not inc or any(p in t for p in inc)) and not any(p in t for p in exc)
                and (desde is None or (n.fecha is not None and n.fecha >= desde)))
    return [n for n in noticias if ok(n)]


def ultimas_horas(ahora: datetime, horas: int) -> datetime:
    """Momento de corte para "las últimas N horas"."""
    return ahora - timedelta(hours=horas)


def texto_resumen(noticias: list[Noticia]) -> str:
    """Lista numerada en texto plano (cuerpo del email y salida de consola)."""
    if not noticias:
        return "Sin titulares nuevos."
    lineas = []
    for i, n in enumerate(noticias, 1):
        f = f"{n.fecha:%d/%m %H:%M} · " if n.fecha else ""
        lineas.append(f"{i}. {n.titulo}\n   {f}{n.fuente}\n   {n.enlace}")
    return "\n".join(lineas)


def html_resumen(noticias: list[Noticia]) -> str:
    """HTML simple con todo escapado (los títulos vienen de terceros)."""
    # escape() también escapa comillas, por eso es seguro dentro del atributo href.
    items = "".join(f'<li><a href="{escape(n.enlace)}">{escape(n.titulo)}</a> '
                    f"<small>{escape(n.fuente)}</small><br>{escape(n.resumen)}</li>" for n in noticias)
    return f"<html><body><h2>Titulares</h2><ol>{items}</ol></body></html>"
