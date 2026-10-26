"""Nombres personalizados, guardado seguro e historial de capturas.

La plantilla de nombre admite:

* ``{fecha}`` — fecha/hora, con formato strftime opcional: ``{fecha:%Y-%m-%d}``;
* ``{n}`` — contador de la sesión, con formato opcional: ``{n:03d}``;
* ``{ancho}`` y ``{alto}`` — dimensiones de la imagen.

El resultado se sanea (sin separadores de ruta ni caracteres prohibidos en
Windows), y si el archivo ya existe se añade ``-2``, ``-3``… en vez de
sobrescribirlo.
"""
from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PIL import Image

PLANTILLA_DEFECTO = "captura_{fecha:%Y%m%d_%H%M%S}"
FORMATOS = {"png": "PNG", "jpg": "JPEG", "jpeg": "JPEG", "webp": "WEBP", "bmp": "BMP"}
_PROHIBIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVADOS_WIN = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def sanear(nombre: str) -> str:
    """Convierte cualquier texto en un nombre de archivo seguro (sin extensión)."""
    limpio = _PROHIBIDOS.sub("_", nombre).strip().strip(".")
    limpio = re.sub(r"\s+", " ", limpio)[:150]
    if not limpio or limpio.upper() in _RESERVADOS_WIN:
        limpio = f"_{limpio}" if limpio else "captura"
    return limpio


def generar_nombre(plantilla: str, n: int, tam: tuple[int, int], ahora: datetime) -> str:
    """Aplica la plantilla con ``str.format`` (variables: fecha, n, ancho, alto) y sanea el
    resultado. Un campo desconocido o un formato mal escrito se informa como ValueError
    con un mensaje claro.
    """
    try:
        nombre = plantilla.format(fecha=ahora, n=n, ancho=tam[0], alto=tam[1])
    except (KeyError, IndexError, ValueError) as e:
        raise ValueError(f"plantilla inválida: {e}") from e
    return sanear(nombre)


def ruta_libre(carpeta: Path, base: str, ext: str) -> Path:
    """Primera ruta que no existe: base.ext, base-2.ext, base-3.ext…"""
    ruta = carpeta / f"{base}.{ext}"
    i = 2
    while ruta.exists():
        ruta = carpeta / f"{base}-{i}.{ext}"
        i += 1
    return ruta


def guardar(img: Image.Image, carpeta: Path, base: str, formato: str = "png", calidad: int = 90) -> Path:
    """Guarda de forma atómica (temporal + replace) y devuelve la ruta final."""
    ext = formato.lower().lstrip(".")
    if ext not in FORMATOS:
        raise ValueError(f"formato no soportado: {formato} (usá {', '.join(sorted(FORMATOS))})")
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = ruta_libre(carpeta, sanear(base), ext)
    opciones = {"quality": calidad} if FORMATOS[ext] in ("JPEG", "WEBP") else {"optimize": True}
    fd, tmp = tempfile.mkstemp(dir=carpeta, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            img.convert("RGB").save(f, FORMATOS[ext], **opciones)
        os.replace(tmp, destino)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return destino


class Sesion:
    """Coordina captura → nombre → guardado y lleva el historial de la sesión."""

    def __init__(self, capturador, carpeta: Path, plantilla: str = PLANTILLA_DEFECTO,
                 formato: str = "png", ahora: Callable[[], datetime] = datetime.now) -> None:
        """``capturador`` y ``ahora`` se inyectan para probar sin pantalla y con fecha fija.
        ``contador`` numera las capturas de la sesión (variable {n}) y ``historial``
        guarda las rutas creadas.
        """
        self.capturador = capturador
        self.carpeta = Path(carpeta)
        self.plantilla = plantilla
        self.formato = formato
        self._ahora = ahora
        self.contador = 0
        self.historial: list[Path] = []

    def capturar_y_guardar(self, region=None, nombre: str | None = None) -> Path:
        """Si ``nombre`` viene dado (no vacío), tiene prioridad sobre la plantilla."""
        img = self.capturador.capturar(region)
        self.contador += 1
        base = nombre.strip() if nombre and nombre.strip() else generar_nombre(
            self.plantilla, self.contador, img.size, self._ahora())
        ruta = guardar(img, self.carpeta, base, self.formato)
        self.historial.append(ruta)
        return ruta
