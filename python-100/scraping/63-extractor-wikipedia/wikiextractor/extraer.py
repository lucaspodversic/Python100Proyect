"""Extracción con BeautifulSoup sobre el HTML que devuelve `action=parse`.

- resumen: párrafos antes del primer encabezado, sin referencias [1].
- secciones: encabezados h2/h3 con su nivel.
- infobox: tabla `.infobox` como pares clave → valor.
- tablas: `table.wikitable` → lista de filas, expandiendo colspan/rowspan
  para que cada fila tenga la misma cantidad de columnas.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup, Tag

# Una tabla es una lista de filas; cada fila, una lista de textos.
Tabla = list[list[str]]


def _limpio(nodo: Tag) -> str:
    """Texto de un nodo sin referencias, enlaces de edición ni estilos, con espacios normalizados."""
    # OJO: decompose() modifica la sopa; por eso extraer_articulo usa una sopa por extractor.
    for basura in nodo.select("sup.reference, .mw-editsection, style, .noprint"):
        basura.decompose()
    # get_text(" ") separa nodos con espacio; luego se colapsan espacios y se pegan comas y puntos.
    return re.sub(r"\s+", " ", nodo.get_text(" ")).strip().replace(" ,", ",").replace(" .", ".")


def resumen(sopa: BeautifulSoup, max_parrafos: int = 3) -> str:
    """Primeros párrafos del artículo, antes del primer encabezado."""
    # El contenido vive en .mw-parser-output; si no está, se usa la sopa entera.
    raiz = sopa.select_one(".mw-parser-output") or sopa
    parrafos = []
    # Sólo hijos directos: los párrafos dentro de tablas o cajas no cuentan.
    for hijo in raiz.children:
        # Se saltan textos sueltos y comentarios entre etiquetas.
        if not isinstance(hijo, Tag):
            continue
        # MediaWiki moderno envuelve los encabezados en <div class="mw-heading">.
        if hijo.name in {"h2", "h3"} or "mw-heading" in (hijo.get("class") or []):
            break
        # Se descartan párrafos vacíos.
        if hijo.name == "p" and (t := _limpio(hijo)):
            parrafos.append(t)
    return "\n\n".join(parrafos[:max_parrafos])


def secciones(sopa: BeautifulSoup) -> list[tuple[int, str]]:
    """Encabezados h2/h3 como (nivel, texto)."""
    return [(int(h.name[1]), _limpio(h)) for h in sopa.find_all(["h2", "h3"])]


def infobox(sopa: BeautifulSoup) -> dict[str, str]:
    """Filas th/td de la tabla .infobox como diccionario clave → valor."""
    caja = sopa.select_one("table.infobox")
    if not caja:
        return {}
    datos = {}
    for fila in caja.find_all("tr"):
        th, td = fila.find("th"), fila.find("td")
        # Se ignoran filas de título o imagen que no tienen ambas celdas.
        if th and td:
            datos[_limpio(th)] = _limpio(td)
    return datos


def _tabla_a_filas(t: Tag) -> Tabla:
    """Expande colspan/rowspan en una grilla rectangular."""
    # Cada celda con rowspan "reserva" su texto en las filas siguientes.
    filas: Tabla = []
    pendientes: dict[tuple[int, int], str] = {}  # (fila, col) ocupadas por rowspan
    for i, tr in enumerate(t.find_all("tr")):
        fila: list[str] = []
        col = 0
        # Antes de cada celda se vuelcan las posiciones ya ocupadas por rowspans de arriba.
        for celda in tr.find_all(["th", "td"]):
            while (i, col) in pendientes:
                fila.append(pendientes.pop((i, col))); col += 1
            texto = _limpio(celda)
            # Se quitan caracteres no numéricos ("2;" o "2px" aparecen en HTML real); vacío → 1.
            cs = int(re.sub(r"\D", "", celda.get("colspan", "1")) or 1)
            rs = int(re.sub(r"\D", "", celda.get("rowspan", "1")) or 1)
            # El texto se repite en cada columna que abarca y se reserva para las filas que abarca.
            for _ in range(cs):
                fila.append(texto)
                for k in range(1, rs):
                    pendientes[(i + k, col)] = texto
                col += 1
        # Rowspans que quedan al final de la fila.
        while (i, col) in pendientes:
            fila.append(pendientes.pop((i, col))); col += 1
        if fila:
            filas.append(fila)
    # Se rellenan con "" las filas cortas para que la grilla sea rectangular.
    ancho = max((len(f) for f in filas), default=0)
    return [f + [""] * (ancho - len(f)) for f in filas]


def tablas(sopa: BeautifulSoup) -> list[Tabla]:
    """Todas las tablas .wikitable del artículo como grillas."""
    return [_tabla_a_filas(t) for t in sopa.select("table.wikitable")]


@dataclass
class Articulo:
    """Todo lo extraído de un artículo."""
    titulo: str
    resumen: str
    secciones: list[tuple[int, str]]
    infobox: dict[str, str]
    # default_factory: cada instancia tiene su propia lista.
    tablas: list[Tabla] = field(default_factory=list)

    def guardar_tablas(self, carpeta: Path) -> list[Path]:
        """Guarda cada tabla como <titulo>_tablaN.csv en `carpeta` y devuelve las rutas."""
        carpeta = Path(carpeta); carpeta.mkdir(parents=True, exist_ok=True)
        # Nombre de archivo seguro: "Ejemplo (lenguaje)" → "Ejemplo_lenguaje".
        base = re.sub(r"[^\w-]+", "_", self.titulo).strip("_")
        rutas = []
        for n, t in enumerate(self.tablas, 1):
            r = carpeta / f"{base}_tabla{n}.csv"
            # newline="" lo pide el módulo csv para no duplicar saltos de línea.
            with r.open("w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerows(t)
            rutas.append(r)
        return rutas


def extraer_articulo(titulo: str, html: str) -> Articulo:
    """Arma el Articulo completo a partir del HTML de action=parse."""
    # Cada extractor modifica nodos (decompose): usamos una sopa nueva por extractor
    s = lambda: BeautifulSoup(html, "html.parser")
    return Articulo(titulo, resumen(s()), secciones(s()), infobox(s()), tablas(s()))
