"""Parsers genéricos.

1. `parsear_jsonld`: muchos portales publican las ofertas como datos
   estructurados schema.org `JobPosting` en `<script type="application/ld+json">`.
   Es la vía más robusta porque no depende del diseño visual.
2. `parsear_html`: selectores CSS configurables (`PerfilSelectores`),
   cargables desde JSON, para adaptar el scraper a un sitio permitido
   sin tocar código.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from .modelo import Oferta, parsear_salario


@dataclass(frozen=True)
class PerfilSelectores:
    """Selectores CSS para un sitio; los vacíos se omiten."""
    # Selector de cada oferta del listado; el resto se busca dentro de cada tarjeta.
    tarjeta: str
    titulo: str
    empresa: str
    ubicacion: str = ""
    enlace: str = ""            # selector de <a>; se toma href
    salario: str = ""
    fecha: str = ""
    etiquetas: str = ""
    siguiente: str = ""         # selector del enlace "página siguiente"

    @classmethod
    def desde_json(cls, ruta: Path) -> "PerfilSelectores":
        """Carga un perfil desde un JSON con las mismas claves que los campos."""
        return cls(**json.loads(Path(ruta).read_text(encoding="utf-8")))


def _texto(nodo: Tag, selector: str) -> str:
    """Texto del primer nodo que coincide, con espacios normalizados ("" si no hay)."""
    if not selector:
        return ""
    hallado = nodo.select_one(selector)
    # get_text(" ") separa nodos internos y split/join colapsa saltos y espacios.
    return " ".join(hallado.get_text(" ").split()) if hallado else ""


def _es_remoto(*textos: str) -> bool:
    """True si alguno de los textos menciona trabajo remoto."""
    return any(p in t.lower() for t in textos for p in ("remoto", "remote", "teletrabajo"))


def parsear_html(html: str, perfil: PerfilSelectores, url_base: str = "") -> tuple[list[Oferta], str | None]:
    """Devuelve (ofertas, url de la página siguiente o None)."""
    # Parser de la librería estándar: no requiere lxml.
    sopa = BeautifulSoup(html, "html.parser")
    ofertas = []
    for t in sopa.select(perfil.tarjeta):
        titulo = _texto(t, perfil.titulo)
        if not titulo:
            continue  # tarjeta incompleta (p. ej. publicidad)
        enlace = t.select_one(perfil.enlace) if perfil.enlace else None
        ubic = _texto(t, perfil.ubicacion)
        # El salario viene como texto libre: se interpreta con el parser de salarios.
        smin, smax, mon = parsear_salario(_texto(t, perfil.salario))
        tags = tuple(e.get_text(strip=True) for e in t.select(perfil.etiquetas)) if perfil.etiquetas else ()
        ofertas.append(Oferta(titulo, _texto(t, perfil.empresa), ubic,
                              # Los enlaces relativos (/oferta/101) se convierten en absolutos.
                              urljoin(url_base, enlace["href"]) if enlace and enlace.get("href") else "",
                              smin, smax, mon, _es_remoto(ubic, titulo, *tags), _texto(t, perfil.fecha), tags))
    # Enlace a la página siguiente (paginación); None si es la última.
    sig = sopa.select_one(perfil.siguiente) if perfil.siguiente else None
    return ofertas, (urljoin(url_base, sig["href"]) if sig and sig.get("href") else None)


def _como_lista(x) -> list:
    """Envuelve en lista lo que no lo es (JSON-LD admite ambas formas)."""
    return x if isinstance(x, list) else [x]


def parsear_jsonld(html: str, url_base: str = "") -> list[Oferta]:
    """Extrae todos los JobPosting (también dentro de @graph o listas)."""
    sopa = BeautifulSoup(html, "html.parser")
    ofertas = []
    # Puede haber varios bloques JSON-LD por página.
    for s in sopa.find_all("script", type="application/ld+json"):
        try:
            datos = json.loads(s.string or "")
        except json.JSONDecodeError:
            continue  # JSON-LD mal formado: lo ignoramos
        nodos = []
        # Se aplanan las formas posibles: objeto suelto, lista de objetos y {"@graph": [...]}.
        for d in _como_lista(datos):
            nodos.extend(_como_lista(d.get("@graph", d)) if isinstance(d, dict) else [])
        for n in nodos:
            # Se ignoran otros tipos schema.org (Organization, BreadcrumbList...).
            if not isinstance(n, dict) or n.get("@type") != "JobPosting":
                continue
            org = n.get("hiringOrganization") or {}
            # Se usa la primera ubicación; address puede faltar.
            lugar = _como_lista(n.get("jobLocation") or [{}])[0]
            dir_ = (lugar.get("address") or {}) if isinstance(lugar, dict) else {}
            ubic = ", ".join(x for x in (dir_.get("addressLocality"), dir_.get("addressCountry")) if x)
            sal = (n.get("baseSalary") or {})
            # baseSalary.value puede traer minValue/maxValue (rango) o un único value.
            val = sal.get("value") or {}
            ofertas.append(Oferta(
                n.get("title", "").strip(), org.get("name", "") if isinstance(org, dict) else str(org), ubic,
                urljoin(url_base, n.get("url", "")) if n.get("url") else "",
                val.get("minValue", val.get("value")), val.get("maxValue", val.get("value")),
                # TELECOMMUTE es el valor schema.org para trabajo remoto.
                sal.get("currency", ""), n.get("jobLocationType") == "TELECOMMUTE", n.get("datePosted", "")))
    return ofertas
