"""Motores de audio detrás de una interfaz común.

El controlador solo conoce el protocolo :class:`MotorAudio`; así se puede
cambiar pygame por otra librería o por un *fake* en tests sin tocar nada más.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


class MotorAudio(Protocol):
    """Operaciones mínimas que necesita el reproductor."""

    def cargar(self, ruta: Path) -> None: ...
    def reproducir(self) -> None: ...
    def pausar(self) -> None: ...
    def reanudar(self) -> None: ...
    def detener(self) -> None: ...
    def fijar_volumen(self, volumen: float) -> None: ...
    def sonando(self) -> bool: ...


class MotorPygame:
    """Implementación real con ``pygame.mixer.music`` (streaming desde disco).

    pygame se importa aquí dentro para que el resto del paquete (y los tests)
    funcionen aunque pygame no esté instalado o no haya tarjeta de sonido.
    """

    def __init__(self) -> None:
        """Importa pygame recién acá (no al importar el módulo) e inicializa el mezclador una
        sola vez, así los tests y la GUI sin audio no necesitan pygame.
        """
        import pygame  # import diferido

        self._musica = pygame.mixer.music
        if not pygame.mixer.get_init():
            pygame.mixer.init()

    def cargar(self, ruta: Path) -> None:
        """Carga el archivo en el canal de música de pygame (streaming, no lo lee entero en
        memoria).
        """
        self._musica.load(str(ruta))

    def reproducir(self) -> None:
        """Empieza la pista cargada desde el principio."""
        self._musica.play()

    def pausar(self) -> None:
        """Pausa conservando la posición."""
        self._musica.pause()

    def reanudar(self) -> None:
        """Sigue desde donde se pausó."""
        self._musica.unpause()

    def detener(self) -> None:
        """Detiene y descarta la posición."""
        self._musica.stop()

    def fijar_volumen(self, volumen: float) -> None:
        """Volumen de 0.0 a 1.0 (el controlador ya lo acota)."""
        self._musica.set_volume(volumen)

    def sonando(self) -> bool:
        """True mientras hay audio saliendo."""
        # get_busy() es False también en pausa; el controlador lo tiene en cuenta.
        return bool(self._musica.get_busy())


@dataclass
class MotorFalso:
    """Motor de mentira para tests: registra llamadas y simula el fin de pista."""

    llamadas: list[str] = field(default_factory=list)
    cargada: Path | None = None
    volumen: float = 1.0
    _sonando: bool = False
    fallar_con: set[str] = field(default_factory=set)  # nombres de archivo que "no se pueden abrir"

    def cargar(self, ruta: Path) -> None:
        """Simula la carga; si el nombre está en ``fallar_con`` lanza RuntimeError como lo
        haría pygame con un archivo corrupto.
        """
        if ruta.name in self.fallar_con:
            raise RuntimeError(f"no se pudo abrir {ruta.name}")
        self.cargada = ruta
        self.llamadas.append(f"cargar:{ruta.name}")

    def reproducir(self) -> None:
        """Marca como sonando y registra la llamada."""
        self._sonando = True
        self.llamadas.append("reproducir")

    def pausar(self) -> None:
        """Deja de sonar y registra la llamada."""
        self._sonando = False
        self.llamadas.append("pausar")

    def reanudar(self) -> None:
        """Vuelve a sonar y registra la llamada."""
        self._sonando = True
        self.llamadas.append("reanudar")

    def detener(self) -> None:
        """Deja de sonar y registra la llamada."""
        self._sonando = False
        self.llamadas.append("detener")

    def fijar_volumen(self, volumen: float) -> None:
        """Guarda el volumen para que los tests lo comprueben."""
        self.volumen = volumen

    def sonando(self) -> bool:
        """Estado simulado; ``terminar_pista`` lo pone en False como si la canción hubiera
        terminado.
        """
        return self._sonando

    def terminar_pista(self) -> None:
        """Simula que la canción actual llegó a su fin."""
        self._sonando = False
