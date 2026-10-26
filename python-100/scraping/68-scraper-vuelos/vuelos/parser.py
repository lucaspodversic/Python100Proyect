"""Parser genérico guiado por un *perfil* JSON (selectores CSS o rutas de claves JSON).

Así el código no queda atado a ningún sitio: el usuario describe la estructura
de una fuente que tiene permiso de leer (su propia agencia, un export, una API).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from bs4 import BeautifulSoup

from .modelo import Vuelo, parsear_duracion, parsear_escalas, parsear_precio


@dataclass(frozen=True)
class PerfilVuelos:
    """Selectores CSS relativos a cada tarjeta de resultado.

    'llegada' es opcional: si falta se calcula salida + 'duracion'.
    Fechas en ISO 8601 (atributo 'datetime' de <time> o texto).
    """
    tarjeta: str                    # selector de cada resultado (ej. "li.oferta")
    campos: dict[str, str]          # campo de Vuelo → selector CSS dentro de la tarjeta
    origen_fijo: str = ""           # para páginas de una sola ruta que no repiten el origen
    destino_fijo: str = ""
    moneda_por_defecto: str = "USD"
    atributos: dict[str, str] = field(default_factory=dict)  # campo → atributo HTML a leer

    @classmethod
    def desde_json(cls, texto: str) -> "PerfilVuelos":
        # Claves desconocidas en el JSON → TypeError de dataclass (detecta errores de tipeo).
        return cls(**json.loads(texto))


def _valor(nodo, selector: str, atributo: str | None) -> str:
    """Texto (o atributo) del primer elemento que coincide; "" si no existe."""
    el = nodo.select_one(selector) if selector else None
    if el is None:
        return ""
    if atributo:
        return str(el.get(atributo, ""))
    # <time datetime="..."> trae la fecha legible por máquina: se prefiere al texto visible.
    return str(el.get("datetime") or el.get_text(" ", strip=True))


def _armar(d: dict[str, Any], moneda_def: str) -> Vuelo:
    """Convierte el dict crudo (HTML o JSON) en Vuelo. KeyError/ValueError si falta algo esencial."""
    salida = datetime.fromisoformat(str(d["salida"]))
    # Llegada explícita si existe; si no, se deriva de la duración.
    llegada = (datetime.fromisoformat(str(d["llegada"])) if d.get("llegada")
               else salida + timedelta(minutes=parsear_duracion(str(d["duracion"]))))
    # Precio numérico (APIs) se toma tal cual vía str() para no arrastrar error binario del float;
    # precio texto (HTML) pasa por la normalización de separadores y moneda.
    precio, moneda = (Decimal(str(d["precio"])), "") if isinstance(d["precio"], (int, float)) else parsear_precio(str(d["precio"]))
    esc = d.get("escalas", 0)
    return Vuelo(str(d.get("aerolinea", "")).strip(), str(d.get("numero", "")).strip(),
                 # IATA en mayúsculas: las APIs a veces devuelven "mad".
                 str(d["origen"]).upper(), str(d["destino"]).upper(), salida, llegada,
                 esc if isinstance(esc, int) else parsear_escalas(str(esc)), precio,
                 # Prioridad de moneda: campo explícito > detectada en el texto > la del perfil.
                 d.get("moneda") or moneda or moneda_def)


def parsear_html(html: str, perfil: PerfilVuelos) -> tuple[list[Vuelo], list[str]]:
    """Devuelve (vuelos, errores); una tarjeta rota no invalida las demás."""
    vuelos, errores = [], []
    for i, t in enumerate(BeautifulSoup(html, "html.parser").select(perfil.tarjeta)):
        d = {k: _valor(t, sel, perfil.atributos.get(k)) for k, sel in perfil.campos.items()}
        # Origen/destino: si el perfil no tiene selector (setdefault) o el selector vino vacío (or),
        # se usa el valor fijo del perfil.
        d.setdefault("origen", perfil.origen_fijo); d["origen"] = d["origen"] or perfil.origen_fijo
        d.setdefault("destino", perfil.destino_fijo); d["destino"] = d["destino"] or perfil.destino_fijo
        try:
            vuelos.append(_armar(d, perfil.moneda_por_defecto))
        except (KeyError, ValueError) as exc:
            # Se informa con el índice para poder ubicar la tarjeta en el HTML.
            errores.append(f"tarjeta {i}: {exc}")
    return vuelos, errores


def _ruta(obj: Any, ruta: str) -> Any:
    """'segmentos.0.salida' → obj['segmentos'][0]['salida']."""
    for parte in ruta.split("."):
        # En listas la parte es un índice; en dicts, una clave.
        obj = obj[int(parte)] if isinstance(obj, list) else obj[parte]
    return obj


def parsear_json(datos: dict | list, lista: str, mapeo: dict[str, str], moneda_def: str = "USD") -> tuple[list[Vuelo], list[str]]:
    """Para respuestas de APIs: 'lista' es la ruta a la lista de ofertas; 'mapeo' campo → ruta."""
    vuelos, errores = [], []
    # lista vacía ("") = la raíz ya es la lista de ofertas.
    for i, item in enumerate(_ruta(datos, lista) if lista else datos):
        try:
            vuelos.append(_armar({k: _ruta(item, r) for k, r in mapeo.items()}, moneda_def))
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            # IndexError: segmentos vacíos; TypeError: un nodo no es dict/list. !r muestra el tipo de error.
            errores.append(f"oferta {i}: {exc!r}")
    return vuelos, errores
