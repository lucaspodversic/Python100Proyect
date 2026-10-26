"""Backends de captura detrás de una interfaz común.

* :class:`CapturadorPillow` usa ``PIL.ImageGrab``. Funciona en Windows y macOS;
  en Linux requiere X11 (``xdisplay``). En Wayland suele fallar.
* :class:`CapturadorMss` usa ``mss`` (opcional) y es rápido y multiplataforma.
* :class:`CapturadorFalso` genera una imagen sintética y determinista para tests.

:func:`elegir_capturador` toma el mejor disponible.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from PIL import Image, ImageDraw


class ErrorCaptura(Exception):
    """No se pudo capturar (sin display, sin permisos, región fuera de la pantalla, etc.)."""
    pass


@dataclass(frozen=True)
class Region:
    """Rectángulo en coordenadas de pantalla (izq, arriba, ancho, alto)."""

    x: int
    y: int
    ancho: int
    alto: int

    @classmethod
    def desde_puntos(cls, x1: int, y1: int, x2: int, y2: int) -> "Region":
        """Normaliza un arrastre del ratón en cualquier dirección."""
        x, y = min(x1, x2), min(y1, y2)
        return cls(x, y, abs(x2 - x1), abs(y2 - y1))

    def caja(self) -> tuple[int, int, int, int]:
        """Formato (izq, arriba, der, abajo) que usan Pillow y ``Image.crop``."""
        return (self.x, self.y, self.x + self.ancho, self.y + self.alto)

    def valida(self, minimo: int = 2) -> bool:
        """Descarta selecciones accidentales (un clic sin arrastrar da 0×0)."""
        return self.ancho >= minimo and self.alto >= minimo


class Capturador(Protocol):
    """Interfaz común de los backends de captura (Pillow, mss o el falso de los tests)."""
    nombre: str

    def capturar(self, region: Region | None = None) -> Image.Image:
        """Devuelve la pantalla completa (todas las pantallas) o solo ``region``, en RGB."""
        ...


class CapturadorPillow:
    """Backend por defecto con Pillow ImageGrab: Windows, macOS y Linux con X11 (en Wayland
    puede fallar).
    """
    nombre = "Pillow ImageGrab"

    def capturar(self, region: Region | None = None) -> Image.Image:
        """Captura con ImageGrab y normaliza a RGB (en macOS puede venir con alfa). Los errores
        del sistema se traducen a ErrorCaptura.
        """
        from PIL import ImageGrab
        try:
            # all_screens solo tiene efecto en Windows; en Linux usa el display X11.
            img = ImageGrab.grab(bbox=region.caja() if region else None, all_screens=True)
        except OSError as e:
            raise ErrorCaptura(f"no se pudo capturar la pantalla: {e}") from e
        return img.convert("RGB")


class CapturadorMss:
    """Backend opcional con ``mss``: más rápido y con soporte multi-monitor uniforme."""
    nombre = "mss"

    def __init__(self) -> None:
        """Importa mss recién acá: si no está instalado, ``elegir_capturador`` cae a Pillow."""
        import mss  # import perezoso: dependencia opcional
        self._mss = mss

    def capturar(self, region: Region | None = None) -> Image.Image:
        """mss entrega BGRA; se convierte a RGB descartando el alfa ('BGRX')."""
        with self._mss.mss() as sct:
            mon = ({"left": region.x, "top": region.y, "width": region.ancho, "height": region.alto}
                   if region else sct.monitors[0])  # monitors[0] = todos los monitores
            try:
                shot = sct.grab(mon)
            except self._mss.exception.ScreenShotError as e:
                raise ErrorCaptura(str(e)) from e
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


class CapturadorFalso:
    """Pantalla sintética de 320×200 con un degradado y un rectángulo (determinista)."""

    nombre = "falso"

    def __init__(self, ancho: int = 320, alto: int = 200) -> None:
        """Pantalla simulada de tamaño fijo; cuenta las llamadas."""
        self.ancho, self.alto = ancho, alto
        self.llamadas = 0

    def capturar(self, region: Region | None = None) -> Image.Image:
        """Imagen determinista: degradé por coordenadas y un cuadrado rojo de (50,50) a
        (100,100), así los tests pueden verificar recortes por color. Una región que
        se sale de la pantalla da error, igual que en un backend real.
        """
        self.llamadas += 1
        img = Image.new("RGB", (self.ancho, self.alto))
        img.putdata([(x % 256, y % 256, 128) for y in range(self.alto) for x in range(self.ancho)])
        ImageDraw.Draw(img).rectangle((50, 50, 100, 100), fill=(255, 0, 0))
        if region:
            if region.x + region.ancho > self.ancho or region.y + region.alto > self.alto:
                raise ErrorCaptura("región fuera de la pantalla")
            img = img.crop(region.caja())
        return img


def elegir_capturador() -> Capturador:
    """mss si está instalado; si no, Pillow."""
    try:
        return CapturadorMss()
    except ImportError:
        return CapturadorPillow()
