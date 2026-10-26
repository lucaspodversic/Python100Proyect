"""Controlador: une la lista con el motor de audio y lleva el estado."""
from __future__ import annotations

from enum import Enum
from pathlib import Path

from .audio import MotorAudio
from .lista import ListaReproduccion


class Estado(str, Enum):
    """Estados del reproductor. Hace falta distinguir PAUSADO de DETENIDO porque el motor
    informa 'no sonando' en ambos casos y solo en DETENIDO-por-fin-de-pista hay que
    avanzar.
    """
    DETENIDO = "detenido"
    REPRODUCIENDO = "reproduciendo"
    PAUSADO = "pausado"


class Reproductor:
    """Máquina de estados del reproductor.

    La GUI llama a :meth:`tick` periódicamente (``after``) para detectar el
    fin de pista y pasar a la siguiente; en tests se llama a mano.
    """

    def __init__(self, motor: MotorAudio, lista: ListaReproduccion | None = None) -> None:
        """Recibe el motor por inyección (pygame en la app, MotorFalso en tests) y aplica el
        volumen inicial del 80 %.
        """
        self.motor = motor
        self.lista = lista or ListaReproduccion()
        self.estado = Estado.DETENIDO
        self.volumen = 0.8
        self.errores: list[str] = []   # pistas que no se pudieron abrir
        self.motor.fijar_volumen(self.volumen)

    def _sonar(self, ruta: Path | None) -> None:
        """Carga y reproduce ``ruta``; si falla, la salta (máx. una vuelta)."""
        intentos = len(self.lista)
        while ruta is not None and intentos > 0:
            try:
                self.motor.cargar(ruta)
            except Exception as e:  # archivo corrupto/formato no soportado
                self.errores.append(f"{ruta.name}: {e}")
                intentos -= 1
                ruta = self.lista.siguiente(automatico=True)
                continue
            self.motor.reproducir()
            self.estado = Estado.REPRODUCIENDO
            return
        self.motor.detener()
        self.estado = Estado.DETENIDO

    # ------------------------------------------------------------ acciones
    def reproducir_pausar(self) -> None:
        """Botón ▶/⏸: alterna según el estado actual."""
        if self.estado is Estado.REPRODUCIENDO:
            self.motor.pausar()
            self.estado = Estado.PAUSADO
        elif self.estado is Estado.PAUSADO:
            self.motor.reanudar()
            self.estado = Estado.REPRODUCIENDO
        else:
            self._sonar(self.lista.actual)

    def detener(self) -> None:
        """Detiene el audio; la próxima reproducción empieza la pista desde el principio."""
        self.motor.detener()
        self.estado = Estado.DETENIDO

    def siguiente(self) -> None:
        """Botón ⏭: pasa a la siguiente según el orden (normal o aleatorio) y la hace sonar."""
        self._sonar(self.lista.siguiente())

    def anterior(self) -> None:
        """Botón ⏮: vuelve a la pista anterior (con vuelta al final)."""
        self._sonar(self.lista.anterior())

    def elegir(self, indice: int) -> None:
        """Doble clic en la lista: reproduce la pista de ese índice."""
        self._sonar(self.lista.ir_a(indice))

    def fijar_volumen(self, volumen: float) -> float:
        """Limita a [0, 1] y lo aplica al motor."""
        self.volumen = min(1.0, max(0.0, volumen))
        self.motor.fijar_volumen(self.volumen)
        return self.volumen

    def tick(self) -> None:
        """Si estaba reproduciendo y el motor ya no suena, la pista terminó."""
        if self.estado is Estado.REPRODUCIENDO and not self.motor.sonando():
            self._sonar(self.lista.siguiente(automatico=True))
