"""Extracción del contenido principal con `html.parser` (biblioteca estándar).

Heurística tipo "readability" simplificada:
- Metadatos: og:title / <title> / <h1>, autor (meta author) y fecha (article:published_time / <time>).
- Contenido: se juntan los párrafos (<p>, <h2>, <h3>, <li>) que estén DENTRO de
  <article> si existe (si no, de <main>, si no, del <body>), salteando
  nav, header, footer, aside, form, script y style (menús, publicidad, etc.).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

# Contenedores de "ruido": su texto nunca entra al artículo.
IGNORAR = {"nav", "header", "footer", "aside", "form", "script", "style", "noscript", "svg", "button"}
BLOQUES = {"p", "h2", "h3", "li", "blockquote"}
# No se apilan: como nunca llega su cierre, dejarían la pila desbalanceada.
VACIOS = {"br", "img", "hr", "meta", "link", "input"}   # etiquetas sin cierre


@dataclass
class Articulo:
    titulo: str = ""
    autor: str = ""
    fecha: str = ""
    parrafos: list[str] = field(default_factory=list)

    @property
    def texto(self) -> str:
        return "\n\n".join(self.parrafos)

    @property
    def palabras(self) -> int:
        return len(self.texto.split())


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        # Pila de etiquetas abiertas: permite saber en qué contexto está cada texto.
        self.pila: list[str] = []
        self.meta: dict[str, str] = {}
        self.titulo_tag = self.h1 = self.time = ""
        # párrafos por contenedor, para elegir el mejor al final
        self.parrafos: dict[str, list[str]] = {"article": [], "main": [], "body": []}
        self._buffer: list[str] | None = None

    def _dentro(self, tag: str) -> bool:
        return tag in self.pila

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta":
            # Open Graph usa property="og:title"; los meta clásicos usan name="author".
            clave = a.get("property") or a.get("name")
            if clave and a.get("content"):
                self.meta[clave.lower()] = a["content"].strip()
            return
        if tag in VACIOS:
            return
        self.pila.append(tag)
        # Empieza a acumular texto solo si el bloque no está dentro de ruido.
        if tag in BLOQUES and not any(t in IGNORAR for t in self.pila):
            self._buffer = []
        if tag == "time" and a.get("datetime") and not self.time:
            self.time = a["datetime"]

    def _cerrar_bloque(self, tag: str) -> None:
        """Guarda el texto acumulado del bloque en cada contenedor que lo incluye."""
        if self._buffer is None:
            return
        # Colapsa espacios y saltos de línea múltiples en uno solo.
        texto = " ".join("".join(self._buffer).split())
        if len(texto) >= 25 or tag in ("h2", "h3"):   # descarta fragmentos sueltos
            # Se guarda en TODOS los contenedores que lo rodean; al final se elige el
            # más específico que tenga contenido.
            for cont in ("article", "main", "body"):
                if self._dentro(cont):
                    self.parrafos[cont].append(texto)
        self._buffer = None

    def handle_endtag(self, tag):
        if tag not in self.pila:
            return  # HTML mal formado: se ignora el cierre huérfano
        # Cierra también las etiquetas que quedaron abiertas (p. ej. <p> sin </p>);
        # si alguna era un bloque de texto, se guarda su contenido.
        while self.pila:
            actual = self.pila[-1]
            if actual in BLOQUES:
                self._cerrar_bloque(actual)
            self.pila.pop()
            if actual == tag:
                break

    def handle_data(self, data):
        # Los <svg> pueden traer su propio <title> (accesibilidad): se ignora.
        if self._dentro("title") and not self._dentro("svg"):
            self.titulo_tag += data
        elif self._dentro("h1") and not any(t in IGNORAR for t in self.pila):
            self.h1 += data
        if self._buffer is not None:
            self._buffer.append(data)


def extraer(html: str) -> Articulo:
    p = _Extractor()
    p.feed(html)
    # close() procesa lo que quedó en el buffer del parser al final.
    p.close()
    # Preferencia: <article> > <main> > <body>; lista vacía cuenta como falsa.
    parrafos = p.parrafos["article"] or p.parrafos["main"] or p.parrafos["body"]
    titulo = p.meta.get("og:title") or " ".join(p.titulo_tag.split()) or " ".join(p.h1.split())
    titulo = re.split(r"\s+[|–-]\s+", titulo)[0]   # quita " | Nombre del sitio"
    fecha = p.meta.get("article:published_time") or p.time
    # fecha[:10] deja solo AAAA-MM-DD de un timestamp ISO completo.
    return Articulo(titulo, p.meta.get("author", ""), fecha[:10], parrafos)
