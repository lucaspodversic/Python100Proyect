"""Del HTML al texto comparable.

Comparar el HTML crudo daría falsos positivos (tokens CSRF, scripts,
banners). Por eso:
1. Se quitan <script>, <style>, <noscript>, comentarios.
2. Opcionalmente se toma sólo la región de un selector CSS.
3. Se aplican expresiones "a ignorar" (fechas, contadores…).
4. Se normalizan espacios línea por línea.
"""
from __future__ import annotations

import hashlib
import re

from bs4 import BeautifulSoup, Comment


def extraer_texto(html: str, selector: str | None = None, ignorar: tuple[str, ...] = ()) -> str:
    """Devuelve el texto "estable" de la página (o de la región `selector`).

    Lanza LookupError si el selector no coincide: casi siempre significa que el
    sitio cambió de estructura, y conviene avisarlo en vez de comparar vacío.
    """
    # html.parser es el parser de la stdlib: sin dependencias extra (lxml) y tolerante a HTML roto.
    sopa = BeautifulSoup(html, "html.parser")
    # 1) Elementos que no son contenido visible: código, estilos y plantillas.
    for t in sopa(["script", "style", "noscript", "template"]):
        t.decompose()
    # Comentarios HTML (<!-- -->): suelen tener timestamps de build que cambian siempre.
    for c in sopa.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()
    if selector:
        # 2) Sólo la región de interés; si hay varias coincidencias se unen todas en orden.
        nodos = sopa.select(selector)
        if not nodos:
            raise LookupError(f"El selector {selector!r} no encontró nada")
        texto = "\n".join(n.get_text("\n") for n in nodos)
    else:
        # Sin selector se usa el <body>; si el documento no tiene body (fragmento), la sopa entera.
        texto = (sopa.body or sopa).get_text("\n")
    # 3) Ruido configurable por el usuario (contadores de visitas, fechas, etc.).
    for patron in ignorar:
        texto = re.sub(patron, "", texto)
    # 4) Colapsar espacios internos de cada línea y descartar líneas vacías:
    #    un cambio de indentación o de saltos de línea no es un cambio real.
    lineas = (" ".join(l.split()) for l in texto.splitlines())
    return "\n".join(l for l in lineas if l)


def huella(texto: str) -> str:
    """SHA-256 del texto normalizado: comparar huellas es barato y no depende del largo."""
    return hashlib.sha256(texto.encode()).hexdigest()
