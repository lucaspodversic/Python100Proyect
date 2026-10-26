"""Parsers genéricos: JSON-LD `Review` (schema.org) y selectores CSS configurables."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from .modelo import Resena, parsear_estrellas


@dataclass(frozen=True)
class PerfilResenas:
    """Selectores CSS que describen dónde está cada dato de una reseña en un sitio."""
    # Obligatorios: el contenedor de cada reseña y su texto.
    tarjeta: str
    texto: str
    autor: str = ""
    estrellas: str = ""
    atributo_estrellas: str = ""   # p. ej. "data-rating" o "aria-label"; vacío = texto
    titulo: str = ""
    fecha: str = ""
    verificada: str = ""           # selector cuya presencia indica compra verificada
    siguiente: str = ""

    @classmethod
    def desde_json(cls, ruta: Path) -> "PerfilResenas":
        """Carga un perfil desde un JSON cuyas claves son los nombres de los campos."""
        return cls(**json.loads(Path(ruta).read_text(encoding="utf-8")))


def _t(nodo: Tag, sel: str) -> str:
    """Texto con espacios normalizados del primer nodo que coincide con `sel`; "" si no hay."""
    h = nodo.select_one(sel) if sel else None
    return " ".join(h.get_text(" ").split()) if h else ""


def parsear_html(html: str, p: PerfilResenas, url_base: str = "") -> tuple[list[Resena], str | None]:
    """Extrae reseñas con el perfil y devuelve (reseñas, URL absoluta de la página siguiente o None)."""
    sopa = BeautifulSoup(html, "html.parser")
    res = []
    # Las tarjetas sin texto (publicidad, placeholders) se ignoran.
    for c in sopa.select(p.tarjeta):
        texto = _t(c, p.texto)
        if not texto:
            continue
        # Las estrellas pueden estar en un atributo (data-rating, aria-label) o en el texto del nodo.
        crudo = ""
        if p.estrellas and (n := c.select_one(p.estrellas)):
            crudo = str(n.get(p.atributo_estrellas, "")) if p.atributo_estrellas else n.get_text(" ")
        # "Verificada" = el selector configurado existe dentro de la tarjeta.
        res.append(Resena(_t(c, p.autor) or "anónimo", texto, parsear_estrellas(crudo), _t(c, p.titulo),
                          _t(c, p.fecha), bool(p.verificada and c.select_one(p.verificada))))
    sig = sopa.select_one(p.siguiente) if p.siguiente else None
    # urljoin resuelve enlaces relativos como "?p=2" contra la URL actual.
    return res, (urljoin(url_base, sig["href"]) if sig and sig.get("href") else None)


def parsear_jsonld(html: str) -> list[Resena]:
    """Busca objetos Review (sueltos o dentro de Product.review)."""
    sopa = BeautifulSoup(html, "html.parser")
    res = []

    def visitar(o) -> None:
        """Recorre recursivamente el JSON buscando objetos de tipo Review."""
        if isinstance(o, list):
            for x in o:
                visitar(x)
        elif isinstance(o, dict):
            # reviewRating puede faltar o venir en otra escala (bestRating): se normaliza a 5.
            if o.get("@type") == "Review":
                r = o.get("reviewRating") or {}
                tope = float(r.get("bestRating", 5) or 5)
                val = r.get("ratingValue")
                est = round(float(val) * 5 / tope, 2) if val is not None else None
                # author puede ser un objeto Person ({"name": ...}) o un texto suelto.
                autor = o.get("author") or {}
                res.append(Resena(autor.get("name", "anónimo") if isinstance(autor, dict) else str(autor),
                                  (o.get("reviewBody") or "").strip(), est, o.get("name", ""),
                                  o.get("datePublished", "")))
            # Se siguen recorriendo los hijos: así se encuentran las Review dentro de Product.review.
            for v in o.values():
                if isinstance(v, (dict, list)):
                    visitar(v)

    # Un bloque JSON-LD mal formado no detiene el análisis de los demás.
    for s in sopa.find_all("script", type="application/ld+json"):
        try:
            visitar(json.loads(s.string or ""))
        except json.JSONDecodeError:
            continue
    # Sólo cuentan las reseñas con texto.
    return [r for r in res if r.texto]
