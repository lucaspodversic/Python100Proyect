"""Renderizadores a Markdown y HTML autocontenido.

En HTML todo texto proveniente del código se escapa con html.escape
para evitar inyección de marcado (un docstring podría contener <script>).
"""
from __future__ import annotations

import html
import re

from .extractor import Funcion, Modulo


def _ancla(texto: str) -> str:
    """Genera un id apto para anclas: minúsculas, sólo [a-z0-9-]."""
    # "mipkg.sub.mod" → "mipkg-sub-mod"; se quitan guiones sobrantes en los extremos.
    # Nota: los caracteres acentuados también se reemplazan por "-".
    return re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-")


def _md_funcion(f: Funcion, nivel: str) -> list[str]:
    """Renderiza una función/método como encabezado Markdown con firma, decoradores y docstring."""
    # Se marca "async" porque la firma guardada no lo incluye.
    pref = "async " if f.es_async else ""
    salida = [f"{nivel} `{pref}{f.firma}`", ""]
    # La línea de decoradores sólo aparece si hay alguno.
    salida += [f"*Decoradores:* {', '.join('`@' + d + '`' for d in f.decoradores)}", ""] if f.decoradores else []
    salida += [f.docstring or "_Sin documentación._", ""]
    return salida


def a_markdown(modulos: list[Modulo], titulo: str = "Documentación") -> str:
    """Genera un documento Markdown con índice."""
    # Estructura: título, índice con enlaces a anclas, y una sección "##" por módulo.
    l = [f"# {titulo}", "", "## Índice", ""]
    l += [f"- [{m.nombre}](#{_ancla(m.nombre)})" for m in modulos]
    l.append("")
    for m in modulos:
        l += [f"## {m.nombre}", "", m.docstring or "_Sin documentación._", ""]
        for c in m.clases:
            # Las bases se muestran entre paréntesis como en la definición de la clase.
            bases = f"({', '.join(c.bases)})" if c.bases else ""
            l += [f"### clase `{c.nombre}{bases}`", "", c.docstring or "_Sin documentación._", ""]
            for met in c.metodos:
                l += _md_funcion(met, "####")
        for f in m.funciones:
            l += _md_funcion(f, "###")
    # Sin líneas en blanco sobrantes al final y con exactamente un salto de línea final.
    return "\n".join(l).rstrip() + "\n"


# Estilos mínimos embebidos: la página no depende de archivos ni de CDNs externos.
CSS = ("body{font-family:system-ui,sans-serif;max-width:900px;margin:auto;padding:1rem;line-height:1.5}"
       "code,pre{background:#f4f4f4;border-radius:4px;padding:.1rem .3rem}pre{padding:.6rem;white-space:pre-wrap}"
       "h2{border-bottom:1px solid #ddd}")


def a_html(modulos: list[Modulo], titulo: str = "Documentación") -> str:
    """Genera una página HTML autocontenida (CSS embebido, sin JS)."""
    # Alias corto: TODO texto que viene del código pasa por e() antes de entrar al HTML.
    e = html.escape
    p = [f"<!doctype html><html lang='es'><head><meta charset='utf-8'><title>{e(titulo)}</title>",
         f"<style>{CSS}</style></head><body><h1>{e(titulo)}</h1><nav><ul>"]
    p += [f"<li><a href='#{_ancla(m.nombre)}'>{e(m.nombre)}</a></li>" for m in modulos]
    p.append("</ul></nav>")
    # Los docstrings van en <pre> para conservar saltos de línea e indentación.
    doc = lambda t: f"<pre>{e(t)}</pre>" if t else "<p><em>Sin documentación.</em></p>"
    for m in modulos:
        # Una <section> por módulo, con el mismo id que usa el índice.
        p.append(f"<section id='{_ancla(m.nombre)}'><h2>{e(m.nombre)}</h2>{doc(m.docstring)}")
        for c in m.clases:
            p.append(f"<h3>clase <code>{e(c.nombre)}</code></h3>{doc(c.docstring)}")
            p += [f"<h4><code>{e(f.firma)}</code></h4>{doc(f.docstring)}" for f in c.metodos]
        p += [f"<h3><code>{e(f.firma)}</code></h3>{doc(f.docstring)}" for f in m.funciones]
        p.append("</section>")
    p.append("</body></html>")
    return "\n".join(p)
