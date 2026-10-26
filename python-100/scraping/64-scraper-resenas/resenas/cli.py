"""CLI: resenas --url URL [--perfil perfil.json] o resenas --archivo pagina.html."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .cliente import BloqueadoPorRobots, ClienteEducado, ErrorHTTP
from .modelo import Resena
from .parser import PerfilResenas, parsear_html, parsear_jsonld
from .resumen import exportar_csv, resumir


def recolectar(html_de, url: str | None, perfil: PerfilResenas | None, max_paginas: int) -> list[Resena]:
    """Recorre páginas: `html_de(url)` devuelve el HTML (red o archivo)."""
    # `vistos` guarda (autor, texto) para no contar dos veces una reseña repetida entre páginas.
    res: list[Resena] = []
    vistos = set()
    paginas = 0
    # Se corta cuando no hay página siguiente o se llegó al tope de páginas.
    while url and paginas < max_paginas:
        html = html_de(url)
        paginas += 1
        # Primero JSON-LD (datos estructurados, más fiables); el perfil CSS es el respaldo.
        nuevas = parsear_jsonld(html)
        sig = None
        # El perfil también aporta el enlace a la página siguiente.
        if perfil:
            css, sig = parsear_html(html, perfil, url)
            nuevas = nuevas or css
        for r in nuevas:
            if (r.autor, r.texto) not in vistos:  # deduplicar entre páginas
                vistos.add((r.autor, r.texto)); res.append(r)
        # Sin perfil o sin enlace "siguiente", sig queda en None y termina el bucle.
        url = sig
    return res


# `cliente` inyectable: los tests usan uno sin pausas contra el servidor local.
def ejecutar(argv: Sequence[str] | None = None, cliente: ClienteEducado | None = None) -> int:
    p = argparse.ArgumentParser(prog="resenas")
    # Exactamente una fuente: --url o --archivo.
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--url", help="página de reseñas de un sitio que permita scraping")
    g.add_argument("--archivo", type=Path, help="HTML guardado localmente (p. ej. de tu propia tienda)")
    p.add_argument("--perfil", type=Path)
    p.add_argument("--paginas", type=int, default=5)
    p.add_argument("--csv", type=Path)
    a = p.parse_args(argv)
    perfil = PerfilResenas.desde_json(a.perfil) if a.perfil else None
    try:
        if a.archivo:
            # Archivo local: una sola "página", sin red.
            res = recolectar(lambda _u: a.archivo.read_text(encoding="utf-8"), a.archivo.as_uri(), perfil, 1)
        else:
            # Red: cliente educado con 3 s entre pedidos, robots.txt y User-Agent honesto.
            c = cliente or ClienteEducado(intervalo=3.0)
            res = recolectar(lambda u: c.get(u).texto(), a.url, perfil, a.paginas)
    # Código 3 distinto para "no permitido", así se distingue de un error común (1).
    except BloqueadoPorRobots as exc:
        print(f"robots.txt no permite {exc}", file=sys.stderr); return 3
    except (ErrorHTTP, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr); return 1
    s = resumir(res)
    # `or '-'` muestra un guion si ninguna reseña tenía estrellas.
    print(f"Reseñas: {s.cantidad}  ·  Promedio: {s.promedio_estrellas or '-'} ★  ·  Sentimiento medio: {s.sentimiento_medio:+}")
    for k, v in s.distribucion.items():
        # Histograma de texto: una barra por cantidad de reseñas con k estrellas.
        print(f"  {k}★ {'█' * v} {v}")
    print(f"Sentimientos: {s.sentimientos}")
    print(f"Lo que gusta: {', '.join(s.temas_positivos) or '-'}")
    print(f"Lo que molesta: {', '.join(s.temas_negativos) or '-'}")
    # Aviso de reseñas cuyo texto contradice las estrellas.
    if s.discrepancias:
        print(f"⚠ {s.discrepancias} reseña(s) con estrellas y texto contradictorios")
    if a.csv:
        exportar_csv(res, a.csv); print(f"CSV: {a.csv}")
    return 0


def main() -> None:
    sys.exit(ejecutar())
