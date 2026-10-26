"""Parseo de líneas de log de acceso.

Formatos soportados (los dos que Apache y Nginx traen por defecto):

* **Common Log Format (CLF)**::

    127.0.0.1 - frank [10/Oct/2000:13:55:36 -0700] "GET /a.gif HTTP/1.0" 200 2326

* **Combined** (CLF + referer + user-agent; ``combined`` en Nginx y Apache)::

    ... 200 2326 "http://ejemplo.com/" "Mozilla/5.0 ..."

Nginx puede agregar campos al final (p. ej. ``$request_time``): se ignoran.
Las líneas que no encajan se cuentan como inválidas en lugar de abortar: los
logs reales tienen basura (peticiones TLS a puerto HTTP, escaneos, etc.).
"""
from __future__ import annotations

import gzip
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

# Expresión regular comentada (re.VERBOSE ignora espacios y permite comentarios).
PATRON = re.compile(r"""
    ^(?P<ip>\S+)\s+                  # IP del cliente (v4 o v6)
    (?P<ident>\S+)\s+                # identd: casi siempre "-"
    (?P<usuario>\S+)\s+              # usuario autenticado o "-"
    \[(?P<fecha>[^\]]+)\]\s+         # [10/Oct/2000:13:55:36 -0700]
    "(?P<peticion>(?:[^"\\]|\\.)*)"\s+   # "GET /ruta HTTP/1.1" (admite \" escapadas)
    (?P<estado>\d{3})\s+             # código de estado HTTP
    (?P<bytes>\d+|-)                 # bytes enviados ("-" = 0)
    (?:\s+"(?P<referer>(?:[^"\\]|\\.)*)"\s+"(?P<agente>(?:[^"\\]|\\.)*)")?   # sólo en combined
    """, re.VERBOSE)

# Apache/Nginx escriben los meses en inglés (Jan, Feb…). strptime con %b depende
# del locale del sistema, así que mapeamos los nombres a mano.
MESES = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}


@dataclass(frozen=True)
class Registro:
    """Una línea del log en formato combinado (Apache/Nginx) ya interpretada. '-' en usuario,
    referer o agente se guarda como None.
    """
    ip: str
    usuario: str | None
    fecha: datetime          # con zona horaria
    metodo: str
    ruta: str                # sin query string, decodificada (%20 → espacio)
    query: str
    protocolo: str
    estado: int
    bytes: int
    referer: str | None
    agente: str | None


def parsear_fecha(texto: str) -> datetime:
    """'10/Oct/2000:13:55:36 -0700' → datetime con tz, independiente del locale."""
    m = re.fullmatch(r"(\d{2})/(\w{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2}) ([+-]\d{4})", texto)
    if not m or m.group(2) not in MESES:
        raise ValueError(f"fecha inválida: {texto}")
    d, mes, a, hh, mm, ss, tz = m.groups()
    # Reconstruimos con mes numérico y usamos strptime solo para la parte numérica + zona.
    return datetime.strptime(f"{a}-{MESES[mes]:02d}-{d} {hh}:{mm}:{ss} {tz}", "%Y-%m-%d %H:%M:%S %z")


def _guion(v: str | None) -> str | None:
    """En los logs, "-" significa "sin valor"."""
    return None if v in (None, "-", "") else v


def parsear_linea(linea: str) -> Registro | None:
    """Devuelve un Registro o None si la línea no es válida."""
    m = PATRON.match(linea.strip())
    if not m:
        return None
    partes = m["peticion"].split()
    # Una petición normal tiene 3 partes; HTTP/0.9 o basura pueden tener menos.
    if len(partes) == 3:
        metodo, objetivo, protocolo = partes
    elif len(partes) == 2:
        (metodo, objetivo), protocolo = partes, "HTTP/0.9"
    else:
        return None
    try:
        fecha = parsear_fecha(m["fecha"])
    except ValueError:
        return None
    url = urlsplit(objetivo)
    return Registro(
        ip=m["ip"], usuario=_guion(m["usuario"]), fecha=fecha, metodo=metodo.upper(),
        ruta=unquote(url.path) or "/", query=url.query, protocolo=protocolo,
        estado=int(m["estado"]), bytes=0 if m["bytes"] == "-" else int(m["bytes"]),
        referer=_guion(m["referer"]), agente=_guion(m["agente"]),
    )


def abrir(ruta: Path) -> Iterator[str]:
    """Itera líneas de un archivo, descomprimiendo si termina en .gz (logrotate lo hace así).
    ``errors="replace"``: un byte inválido no debe tirar abajo el análisis de un log de GBs."""
    abridor = gzip.open if ruta.suffix == ".gz" else open
    with abridor(ruta, "rt", encoding="utf-8", errors="replace") as f:  # type: ignore[operator]
        yield from f


@dataclass
class Lectura:
    """Resultado de leer: registros válidos + cuántas líneas se descartaron (y ejemplos)."""
    registros: list[Registro]
    invalidas: int
    ejemplos_invalidos: list[str]


def leer(lineas: Iterable[str], max_ejemplos: int = 5) -> Lectura:
    """Parsea línea por línea sin cortar ante errores: cuenta las inválidas y guarda hasta
    ``max_ejemplos`` (recortadas a 200 caracteres) para mostrarlas al usuario.
    """
    regs, malas, ejemplos = [], 0, []
    for linea in lineas:
        if not linea.strip():
            continue  # las líneas vacías no cuentan como errores
        r = parsear_linea(linea)
        if r is None:
            malas += 1
            if len(ejemplos) < max_ejemplos:
                ejemplos.append(linea.rstrip()[:200])
        else:
            regs.append(r)
    return Lectura(regs, malas, ejemplos)
