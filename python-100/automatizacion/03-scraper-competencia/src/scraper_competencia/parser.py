"""Extracción de productos desde HTML con BeautifulSoup + selectores CSS."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from .fetcher import Fetcher
from .modelos import Producto, ReglasSitio


def parsear_precio(texto: str) -> Decimal | None:
    """Convierte textos de precio en ``Decimal`` soportando formatos regionales.

    Ejemplos: ``"$ 1.234,56"`` -> 1234.56 (es-AR), ``"US$1,234.56"`` -> 1234.56,
    ``"€ 99"`` -> 99. Devuelve ``None`` si no hay número.

    Heurística: el *último* separador (``.`` o ``,``) seguido de 1-2 dígitos al
    final es el separador decimal; el resto son separadores de miles.
    """
    # Se descarta todo menos dígitos y separadores: "US$ 1,234.56" → "1,234.56".
    limpio = re.sub(r"[^\d.,]", "", texto)
    if not re.search(r"\d", limpio):
        return None
    # Separador final seguido de 1-2 dígitos = decimales. Caso borde: "45.000" tiene 3 dígitos
    # tras el punto, así que NO se toma como decimal y queda 45000 (convención es-AR de miles).
    m = re.search(r"[.,](\d{1,2})$", limpio)
    if m:
        entero = re.sub(r"[.,]", "", limpio[: m.start()])
        numero = f"{entero}.{m.group(1)}"
    else:
        numero = re.sub(r"[.,]", "", limpio)
    try:
        return Decimal(numero)
    except InvalidOperation:  # pragma: no cover - defensivo
        return None


def _texto(tarjeta: Tag, selector: str | None) -> str | None:
    """Texto limpio del primer elemento que matchea, o ``None``."""
    if not selector:
        return None
    el = tarjeta.select_one(selector)
    return el.get_text(" ", strip=True) if el else None


def extraer_productos(html: str, reglas: ReglasSitio, url_base: str = "") -> list[Producto]:
    """Aplica las reglas a una página y devuelve los productos encontrados.

    Las tarjetas sin título se descartan (suelen ser banners o placeholders).
    """
    # "html.parser" es el parser de la biblioteca estándar: sin dependencias nativas (lxml).
    sopa = BeautifulSoup(html, "html.parser")
    productos: list[Producto] = []
    for tarjeta in sopa.select(reglas.tarjeta):
        titulo = _texto(tarjeta, reglas.titulo)
        if not titulo:
            continue
        precio_txt = _texto(tarjeta, reglas.precio) or ""
        # Los href suelen ser relativos ("/p/a1"): ``urljoin`` los resuelve contra la URL de la página.
        url = None
        if reglas.enlace:
            a = tarjeta.select_one(reglas.enlace)
            if a is not None and a.get("href"):
                url = urljoin(url_base, str(a["href"]))
        # Las columnas extra ausentes en una tarjeta quedan como cadena vacía (no rompen el reporte).
        extras = {col: (_texto(tarjeta, sel) or "") for col, sel in reglas.extras.items()}
        productos.append(
            Producto(reglas.nombre, titulo, parsear_precio(precio_txt), _texto(tarjeta, reglas.sku), url, extras)
        )
    return productos


def siguiente_pagina(html: str, reglas: ReglasSitio, url_base: str) -> str | None:
    """URL absoluta de la página siguiente (paginación), si existe."""
    if not reglas.siguiente:
        return None
    a = BeautifulSoup(html, "html.parser").select_one(reglas.siguiente)
    return urljoin(url_base, str(a["href"])) if a is not None and a.get("href") else None


def recorrer(fetcher: Fetcher, url_inicial: str, reglas: ReglasSitio, max_paginas: int = 20) -> list[Producto]:
    """Recorre la paginación hasta ``max_paginas`` (cota anti-bucles)."""
    productos: list[Producto] = []
    url: str | None = url_inicial
    vistas: set[str] = set()
    # Tres condiciones de corte: no hay "siguiente", la URL ya se visitó (paginación circular)
    # o se alcanzó la cota máxima de páginas (protección contra bucles y sobrecarga del sitio).
    while url and url not in vistas and len(vistas) < max_paginas:
        vistas.add(url)
        html = fetcher.obtener(url)
        productos += extraer_productos(html, reglas, url)
        url = siguiente_pagina(html, reglas, url)
    return productos
