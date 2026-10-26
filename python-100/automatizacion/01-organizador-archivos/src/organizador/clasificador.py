"""Reglas de clasificación de archivos.

Este módulo es *puro*: recibe rutas y metadatos y devuelve la carpeta
relativa donde debería ir cada archivo. No toca el disco salvo para leer
``stat`` (fecha de modificación y tamaño), lo que lo hace fácil de testear.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Literal

# Mapa categoría -> extensiones (en minúsculas, sin punto).
# Se puede extender fácilmente agregando claves nuevas.
CATEGORIAS: dict[str, set[str]] = {
    "imagenes": {"jpg", "jpeg", "png", "gif", "bmp", "webp", "svg", "heic", "tiff"},
    "documentos": {"pdf", "doc", "docx", "odt", "txt", "rtf", "md"},
    "hojas_calculo": {"xls", "xlsx", "ods", "csv"},
    "presentaciones": {"ppt", "pptx", "odp", "key"},
    "audio": {"mp3", "wav", "flac", "ogg", "m4a", "aac"},
    "video": {"mp4", "mkv", "avi", "mov", "webm"},
    "comprimidos": {"zip", "rar", "7z", "tar", "gz", "bz2", "xz"},
    "codigo": {"py", "js", "ts", "java", "c", "cpp", "rs", "go", "html", "css", "json"},
    "ejecutables": {"exe", "msi", "deb", "rpm", "dmg", "appimage"},
}

# Categoría por defecto para extensiones desconocidas o archivos sin extensión.
OTROS = "otros"

# Modos de clasificación soportados por la CLI.
Modo = Literal["tipo", "fecha", "tipo_fecha", "tamano"]

# Umbrales (en bytes) para el modo "tamano".
UMBRALES_TAMANO: list[tuple[int, str]] = [
    (1024 * 1024, "pequenos_<1MB"),
    (100 * 1024 * 1024, "medianos_1-100MB"),
]
GRANDES = "grandes_>100MB"


def categoria_de(ruta: Path) -> str:
    """Devuelve la categoría de un archivo según su extensión.

    La comparación es insensible a mayúsculas: ``FOTO.JPG`` es imagen.
    Las extensiones compuestas como ``.tar.gz`` se resuelven por la última
    parte (``gz``), que igualmente cae en "comprimidos".
    """
    # ``suffix`` devuelve sólo la última extensión (".gz" en "x.tar.gz") con el punto incluido;
    # lo normalizamos a minúsculas y sin punto para compararlo contra los sets de CATEGORIAS.
    ext = ruta.suffix.lower().lstrip(".")
    # Recorrido lineal: con ~10 categorías es más simple (y igual de rápido) que un índice inverso.
    # Los dicts preservan el orden de inserción, así que ante una extensión repetida gana la primera.
    for categoria, extensiones in CATEGORIAS.items():
        if ext in extensiones:
            return categoria
    # Caso borde: archivo sin extensión ("Makefile") o extensión desconocida → "otros".
    return OTROS


def carpeta_por_tamano(tamano: int) -> str:
    """Traduce un tamaño en bytes a un nombre de carpeta legible."""
    # Los umbrales están ordenados de menor a mayor: el primero que supere al tamaño define la carpeta.
    for limite, nombre in UMBRALES_TAMANO:
        if tamano < limite:
            return nombre
    # Si no entró en ningún umbral, es mayor o igual a 100 MB.
    return GRANDES


def fecha_de(ruta: Path) -> _dt.datetime:
    """Fecha de modificación del archivo (metadato portable entre SO)."""
    # Usamos mtime y no ctime: en Linux ctime es "cambio de metadatos", no la creación,
    # y en Windows significa otra cosa. mtime es el único con semántica común.
    return _dt.datetime.fromtimestamp(ruta.stat().st_mtime)


def clasificar(ruta: Path, modo: Modo = "tipo") -> Path:
    """Calcula la carpeta *relativa* destino según el modo elegido.

    - ``tipo``: ``imagenes/``
    - ``fecha``: ``2024/03/``
    - ``tipo_fecha``: ``imagenes/2024/03/``
    - ``tamano``: ``pequenos_<1MB/``
    """
    # Cada modo devuelve una ruta RELATIVA; la raíz destino la agrega ``planificar``.
    if modo == "tipo":
        return Path(categoria_de(ruta))
    if modo == "fecha":
        f = fecha_de(ruta)
        # Ceros a la izquierda ("03") para que las carpetas ordenen bien alfabéticamente.
        return Path(f"{f.year:04d}") / f"{f.month:02d}"
    if modo == "tipo_fecha":
        f = fecha_de(ruta)
        return Path(categoria_de(ruta)) / f"{f.year:04d}" / f"{f.month:02d}"
    if modo == "tamano":
        return Path(carpeta_por_tamano(ruta.stat().st_size))
    # Si llega un modo inválido preferimos fallar fuerte antes que mover mal.
    raise ValueError(f"Modo de clasificación desconocido: {modo!r}")


def renombrar(ruta: Path, plantilla: str | None, indice: int) -> str:
    """Genera el nuevo nombre de archivo a partir de una plantilla.

    Variables disponibles en la plantilla (sintaxis ``str.format``):
    ``{nombre}`` (sin extensión), ``{ext}``, ``{fecha}`` (AAAA-MM-DD),
    ``{categoria}`` e ``{indice}`` (contador, admite formato ``{indice:04d}``).

    Si ``plantilla`` es ``None`` se conserva el nombre original.
    """
    # Sin plantilla (None o cadena vacía) no se renombra: se conserva el nombre original.
    if not plantilla:
        return ruta.name
    f = fecha_de(ruta)
    ext = ruta.suffix.lower()
    # ``str.format`` permite especificadores como ``{indice:04d}``. Una variable inexistente
    # en la plantilla lanza KeyError, que preferimos a generar nombres silenciosamente rotos.
    nuevo = plantilla.format(
        nombre=ruta.stem,
        ext=ext.lstrip("."),
        fecha=f.strftime("%Y-%m-%d"),
        categoria=categoria_de(ruta),
        indice=indice,
    )
    # Normalizamos: si la plantilla no incluyó extensión, la agregamos.
    if ext and not nuevo.lower().endswith(ext):
        nuevo += ext
    # Evitamos separadores de ruta en el nombre para no "escapar" del destino.
    return nuevo.replace("/", "_").replace("\\", "_")
