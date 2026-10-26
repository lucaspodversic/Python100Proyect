"""Lógica del visor sin Tkinter: galería, zoom, transformaciones y metadatos.

Todo opera sobre objetos ``PIL.Image`` y números, así que se testea sin
pantalla. La GUI solo convierte el resultado a ``ImageTk.PhotoImage``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

EXTENSIONES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
ZOOM_MIN, ZOOM_MAX = 0.05, 16.0
PASO_ZOOM = 1.25
# Pillow lanza DecompressionBombError por encima de 2× este valor: protege de
# imágenes diminutas en disco que ocupan gigas al descomprimirse.
Image.MAX_IMAGE_PIXELS = 100_000_000


class ErrorImagen(Exception):
    """La imagen no se pudo abrir (formato desconocido, corrupta, demasiado grande)."""


def listar(carpeta: Path) -> list[Path]:
    """Imágenes de ``carpeta`` (no recursivo) en orden natural por nombre."""
    import re

    def natural(p: Path) -> list[object]:
        """Clave de orden natural: parte el nombre en texto y números."""
        # "img10" va después de "img9": se comparan los números como números.
        return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)]

    return sorted((p for p in carpeta.iterdir() if p.is_file() and p.suffix.lower() in EXTENSIONES), key=natural)


def abrir(ruta: Path) -> Image.Image:
    """Abre la imagen aplicando la orientación EXIF (fotos de móvil giradas)."""
    try:
        with Image.open(ruta) as im:
            im.load()
            return ImageOps.exif_transpose(im)
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as e:
        raise ErrorImagen(f"{ruta.name}: {e}") from e


def info(im: Image.Image, ruta: Path | None = None) -> dict[str, object]:
    """Datos para la barra de estado. El formato sale de Pillow o, si la imagen ya fue
    transformada (pierde .format), de la extensión del archivo.
    """
    datos: dict[str, object] = {"ancho": im.width, "alto": im.height, "modo": im.mode,
                                "formato": im.format or (ruta.suffix[1:].upper() if ruta else "?")}
    if ruta is not None and ruta.exists():
        datos["bytes"] = ruta.stat().st_size
    return datos


def zoom_ajustado(ancho: int, alto: int, caja_ancho: int, caja_alto: int, ampliar: bool = False) -> float:
    """Factor para que la imagen quepa en la caja. Por defecto no amplía (máx. 1.0)."""
    if ancho <= 0 or alto <= 0 or caja_ancho <= 0 or caja_alto <= 0:
        return 1.0
    factor = min(caja_ancho / ancho, caja_alto / alto)
    return max(ZOOM_MIN, factor if ampliar else min(1.0, factor))


@dataclass
class Galeria:
    """Lista de imágenes con posición actual y navegación circular."""

    rutas: list[Path] = field(default_factory=list)
    pos: int = 0

    @classmethod
    def desde(cls, ruta: Path) -> "Galeria":
        """Desde una carpeta, o desde un archivo (abre su carpeta y se sitúa en él)."""
        if ruta.is_dir():
            return cls(listar(ruta))
        rutas = listar(ruta.parent)
        return cls(rutas, rutas.index(ruta) if ruta in rutas else 0)

    @property
    def actual(self) -> Path | None:
        """Ruta de la imagen actual o None si la galería está vacía."""
        return self.rutas[self.pos] if self.rutas else None

    def mover(self, delta: int) -> Path | None:
        """Avanza o retrocede ``delta`` posiciones con vuelta (módulo). En una galería vacía
        devuelve None.
        """
        if self.rutas:
            self.pos = (self.pos + delta) % len(self.rutas)
        return self.actual

    def quitar_actual(self) -> None:
        """Quita la imagen actual (p. ej. si no se pudo abrir).

        La posición pasa a la imagen que venía después; si era la última, se
        da la vuelta a la primera (coherente con la navegación circular).
        """
        if self.rutas:
            del self.rutas[self.pos]
            if self.pos >= len(self.rutas):
                self.pos = 0


@dataclass
class Vista:
    """Estado de visualización: zoom, rotación (múltiplos de 90°) y espejos."""

    zoom: float = 1.0
    rotacion: int = 0       # grados antihorarios: 0, 90, 180, 270
    espejo_h: bool = False
    espejo_v: bool = False

    def acercar(self) -> float:
        """Multiplica el zoom por PASO_ZOOM (1.25) sin pasar de ZOOM_MAX (16×)."""
        self.zoom = min(ZOOM_MAX, self.zoom * PASO_ZOOM)
        return self.zoom

    def alejar(self) -> float:
        """Divide el zoom por PASO_ZOOM sin bajar de ZOOM_MIN (5 %)."""
        self.zoom = max(ZOOM_MIN, self.zoom / PASO_ZOOM)
        return self.zoom

    def rotar(self, grados: int) -> None:
        """Rota en múltiplos de 90° (positivo = antihorario, como Pillow). Se normaliza a
        0..359: rotar -90 desde 0 da 270.
        """
        if grados % 90:
            raise ValueError("solo múltiplos de 90°")
        self.rotacion = (self.rotacion + grados) % 360

    def reiniciar(self) -> None:
        """Vuelve a zoom 1, sin rotación ni espejo (al cambiar de imagen)."""
        self.zoom, self.rotacion, self.espejo_h, self.espejo_v = 1.0, 0, False, False

    def transformar(self, im: Image.Image) -> Image.Image:
        """Aplica espejos y rotación (sin pérdida: transpose, no rotate con interpolación)."""
        if self.espejo_h:
            im = im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if self.espejo_v:
            im = im.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        giro = {90: Image.Transpose.ROTATE_90, 180: Image.Transpose.ROTATE_180,
                270: Image.Transpose.ROTATE_270}.get(self.rotacion)
        return im.transpose(giro) if giro else im

    def renderizar(self, im: Image.Image) -> Image.Image:
        """Imagen lista para mostrar: transformada y escalada al zoom actual."""
        im = self.transformar(im)
        tam = (max(1, round(im.width * self.zoom)), max(1, round(im.height * self.zoom)))
        if tam == im.size:
            return im
        # LANCZOS al reducir (mejor calidad); NEAREST al ampliar mucho (ver píxeles).
        filtro = Image.Resampling.NEAREST if self.zoom >= 4 else Image.Resampling.LANCZOS
        return im.resize(tam, filtro)


def guardar_transformada(im: Image.Image, vista: Vista, destino: Path) -> Path:
    """Guarda una copia con la rotación/espejos aplicados (sin el zoom)."""
    salida = vista.transformar(im)
    if destino.suffix.lower() in {".jpg", ".jpeg"} and salida.mode in {"RGBA", "P", "LA"}:
        salida = salida.convert("RGB")  # JPEG no admite transparencia
    salida.save(destino)
    return destino
