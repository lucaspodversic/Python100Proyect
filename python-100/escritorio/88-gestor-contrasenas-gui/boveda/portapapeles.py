"""Copia al portapapeles con **borrado automático**.

Detrás de dos interfaces para poder testearlo sin Tk:

* ``Portapapeles``: leer/escribir/limpiar (Tk real o falso).
* ``programar(ms, fn)``: planificador (``widget.after`` o falso).

Solo se borra si el contenido sigue siendo el que copiamos: si el usuario
copió otra cosa mientras tanto, no se la pisamos.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Protocol


class Portapapeles(Protocol):
    """Interfaz mínima de portapapeles, para poder sustituir el real por uno falso en tests."""

    def leer(self) -> str:
        """Contenido actual como texto."""
        ...

    def escribir(self, texto: str) -> None:
        """Reemplaza el contenido."""
        ...

    def limpiar(self) -> None:
        """Deja el portapapeles vacío."""
        ...


class PortapapelesTk:
    """Adaptador sobre el portapapeles de Tk."""

    def __init__(self, widget) -> None:  # widget: tk.Misc
        """Usa el portapapeles del sistema a través de cualquier widget Tk."""
        self.w = widget

    def leer(self) -> str:
        """Devuelve '' si está vacío o no tiene texto, en vez de lanzar TclError."""
        try:
            return self.w.clipboard_get()
        except Exception:  # TclError si está vacío o tiene datos no textuales
            return ""

    def escribir(self, texto: str) -> None:
        """Escribe y fuerza ``update`` para que otras aplicaciones lo vean."""
        self.w.clipboard_clear()
        self.w.clipboard_append(texto)
        self.w.update()  # en X11 hace falta para que otras apps lo vean

    def limpiar(self) -> None:
        """Vacía el portapapeles del sistema."""
        self.w.clipboard_clear()
        self.w.clipboard_append("")
        self.w.update()


class CopiaSegura:
    """Copia un secreto y lo borra a los N segundos, pero solo si sigue siendo lo que copiamos
    (no pisa algo que el usuario copió después). Cada copia nueva invalida el
    temporizador de la anterior mediante un número de generación.
    """
    def __init__(self, portapapeles: Portapapeles, programar: Callable[[int, Callable[[], None]], object],
                 segundos: int = 20) -> None:
        """``programar(ms, fn)`` es ``widget.after`` en la app o un planificador falso en
        tests.
        """
        self.pp, self.programar, self.segundos = portapapeles, programar, segundos
        self._copiado: str | None = None
        self._generacion = 0   # invalida temporizadores de copias anteriores

    def copiar(self, secreto: str) -> None:
        """Copia y programa el borrado con la generación actual."""
        self.pp.escribir(secreto)
        self._copiado = secreto
        self._generacion += 1
        gen = self._generacion
        self.programar(self.segundos * 1000, lambda: self._expirar(gen))

    def _expirar(self, generacion: int) -> None:
        """Callback del temporizador: ignora generaciones viejas."""
        if generacion != self._generacion:
            return  # hubo otra copia después; su propio temporizador se encargará
        self.limpiar_ahora()

    def limpiar_ahora(self) -> None:
        """Borra si el portapapeles aún contiene nuestro secreto (también al bloquear/salir)."""
        if self._copiado is not None and self.pp.leer() == self._copiado:
            self.pp.limpiar()
        self._copiado = None


class PortapapelesFalso:
    """Implementación en memoria para tests."""

    def __init__(self) -> None:
        """Portapapeles en memoria para tests."""
        self.contenido = ""

    def leer(self) -> str:
        """Contenido simulado."""
        return self.contenido

    def escribir(self, texto: str) -> None:
        """Reemplaza el contenido simulado."""
        self.contenido = texto

    def limpiar(self) -> None:
        """Vacía el contenido simulado."""
        self.contenido = ""
