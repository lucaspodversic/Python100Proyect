"""Lógica del editor, independiente de Tkinter.

- :class:`Documento`: abrir/guardar con detección de codificación, fin de
  línea preservado y escritura **atómica** (archivo temporal + ``os.replace``).
- :func:`buscar` / :func:`reemplazar`: búsqueda literal o por regex.
- :class:`Recientes`: lista de archivos recientes (MRU) persistida en JSON.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# Orden de prueba al abrir. latin-1 nunca falla (último recurso). El BOM de
# UTF-8 se detecta aparte: "utf-8-sig" decodifica también UTF-8 sin BOM y, al
# guardar, añadiría un BOM que el archivo original no tenía.
CODIFICACIONES = ("utf-8", "cp1252", "latin-1")
BOM_UTF8 = b"\xef\xbb\xbf"
MAX_BYTES = 20 * 1024 * 1024  # 20 MiB: un Text de Tk se vuelve inusable con más


class ErrorEditor(Exception):
    """Error mostrable al usuario (archivo binario, demasiado grande, regex inválida…)."""


@dataclass
class Documento:
    r"""Archivo de texto abierto. Recuerda su codificación y su fin de línea original para
    guardarlo igual que como vino (un archivo CRLF en cp1252 sigue siendo CRLF en
    cp1252). En memoria el texto siempre usa '\n'.
    """
    ruta: Path | None = None
    texto: str = ""
    codificacion: str = "utf-8"
    fin_linea: str = "\n"
    _guardado: str = ""   # contenido en disco, para saber si hay cambios

    @property
    def nombre(self) -> str:
        """Nombre para el título de la ventana."""
        return self.ruta.name if self.ruta else "Sin título"

    @property
    def modificado(self) -> bool:
        """True si el texto difiere de lo último leído o guardado (comparación de contenido,
        así escribir y borrar lo mismo no cuenta como cambio).
        """
        return self.texto != self._guardado

    @classmethod
    def abrir(cls, ruta: Path) -> "Documento":
        r"""Lee ``ruta`` probando codificaciones y normalizando fines de línea a ``\n``."""
        datos = ruta.read_bytes()
        if len(datos) > MAX_BYTES:
            raise ErrorEditor("archivo demasiado grande")
        if b"\x00" in datos[:8192]:
            raise ErrorEditor("parece un archivo binario")
        candidatas = ("utf-8-sig",) if datos.startswith(BOM_UTF8) else CODIFICACIONES
        for cod in candidatas:
            try:
                texto = datos.decode(cod)
                break
            except UnicodeDecodeError:
                continue
        fin = "\r\n" if "\r\n" in texto else "\n"
        texto = texto.replace("\r\n", "\n")
        return cls(ruta=ruta, texto=texto, codificacion=cod, fin_linea=fin, _guardado=texto)

    def guardar(self, ruta: Path | None = None) -> Path:
        """Guarda de forma atómica: nunca deja el archivo a medio escribir.

        Se escribe en un temporal del mismo directorio y se renombra con
        ``os.replace`` (atómico en POSIX y Windows). Si el proceso muere a
        mitad, el original queda intacto.
        """
        destino = ruta or self.ruta
        if destino is None:
            raise ErrorEditor("falta elegir dónde guardar")
        # "Guardar como" de un archivo con BOM produce UTF-8 limpio; "Guardar" conserva el BOM.
        cod = "utf-8" if self.codificacion == "utf-8-sig" and ruta else self.codificacion
        datos = self.texto.replace("\n", self.fin_linea).encode(cod)
        fd, tmp = tempfile.mkstemp(dir=destino.parent, prefix=f".{destino.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(datos)
                f.flush()
                os.fsync(f.fileno())
            if destino.exists():  # conservar permisos del original
                os.chmod(tmp, destino.stat().st_mode)
            os.replace(tmp, destino)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        self.ruta, self.codificacion, self._guardado = destino, cod, self.texto
        return destino


# ---------------------------------------------------------------- búsqueda
def _patron(consulta: str, regex: bool, mayusculas: bool, palabra: bool) -> re.Pattern[str]:
    r"""Compila la búsqueda según las opciones: literal (escapada) o regex, sensible o no a
    mayúsculas, y 'palabra completa' rodeándola con \b. Errores de regex se convierten
    en ErrorEditor con un mensaje legible.
    """
    if not consulta:
        raise ErrorEditor("búsqueda vacía")
    expr = consulta if regex else re.escape(consulta)
    if palabra:
        expr = rf"\b(?:{expr})\b"
    try:
        return re.compile(expr, 0 if mayusculas else re.IGNORECASE)
    except re.error as e:
        raise ErrorEditor(f"expresión regular inválida: {e}") from e


def buscar(texto: str, consulta: str, *, regex: bool = False, mayusculas: bool = False,
           palabra: bool = False) -> list[tuple[int, int]]:
    """Devuelve las coincidencias como pares ``(inicio, fin)`` en offsets de caracteres."""
    return [(m.start(), m.end()) for m in _patron(consulta, regex, mayusculas, palabra).finditer(texto)
            if m.end() > m.start()]  # ignora coincidencias vacías (p. ej. regex "a*")


def siguiente(coincidencias: list[tuple[int, int]], desde: int) -> tuple[int, int] | None:
    """Primera coincidencia que empieza en ``desde`` o después; si no hay, da la vuelta."""
    for c in coincidencias:
        if c[0] >= desde:
            return c
    return coincidencias[0] if coincidencias else None


def reemplazar(texto: str, consulta: str, nuevo: str, *, regex: bool = False,
               mayusculas: bool = False, palabra: bool = False) -> tuple[str, int]:
    r"""Reemplaza todas las coincidencias. Devuelve ``(texto_nuevo, cantidad)``.

    En modo literal el reemplazo también es literal (``\1`` no se interpreta).
    """
    patron = _patron(consulta, regex, mayusculas, palabra)
    repl = nuevo if regex else (lambda _m: nuevo)
    try:
        return patron.subn(repl, texto)
    except re.error as e:
        raise ErrorEditor(f"reemplazo inválido: {e}") from e


# ---------------------------------------------------------------- utilidades
def estadisticas(texto: str) -> dict[str, int]:
    """Líneas, palabras y caracteres. Un texto vacío tiene 0 líneas (no 1) para que la barra de
    estado no muestre '1 línea' en un documento nuevo.
    """
    return {"lineas": texto.count("\n") + 1 if texto else 0, "palabras": len(texto.split()),
            "caracteres": len(texto)}


def offset_a_indice_tk(texto: str, offset: int) -> str:
    """Convierte un offset de caracteres a índice Tk ``"línea.columna"`` (línea desde 1)."""
    previo = texto[:offset]
    linea = previo.count("\n") + 1
    columna = offset - (previo.rfind("\n") + 1)
    return f"{linea}.{columna}"


@dataclass
class Recientes:
    """Archivos recientes (más reciente primero, sin duplicados, tamaño máximo)."""

    archivo: Path
    maximo: int = 8
    rutas: list[str] = field(default_factory=list)

    @classmethod
    def cargar(cls, archivo: Path, maximo: int = 8) -> "Recientes":
        """Lee la lista desde JSON. Un archivo faltante o corrupto no es error: se empieza con
        la lista vacía. Se descartan entradas que no son texto.
        """
        try:
            rutas = [r for r in json.loads(archivo.read_text("utf-8")) if isinstance(r, str)]
        except (OSError, ValueError):
            rutas = []  # archivo ausente o corrupto: empezar vacío
        return cls(archivo, maximo, rutas[:maximo])

    def agregar(self, ruta: Path) -> None:
        """Pone la ruta (absoluta) primera, sin duplicados, recorta a ``maximo`` y persiste."""
        r = str(ruta.resolve())
        self.rutas = [r, *(x for x in self.rutas if x != r)][: self.maximo]
        self.archivo.parent.mkdir(parents=True, exist_ok=True)
        self.archivo.write_text(json.dumps(self.rutas, ensure_ascii=False), "utf-8")
