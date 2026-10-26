"""Lógica de tiempo sin Tkinter, con relojes inyectables.

* Cronómetro y temporizador usan un reloj **monotónico** (``time.monotonic``):
  no salta si el usuario cambia la hora del sistema o hay cambio de horario.
* Las alarmas usan la hora de pared (``datetime``), porque "despertame a las
  7:00" se refiere al reloj de la pared.

En tests se pasan relojes falsos y no hay ninguna espera real.
"""
from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from datetime import time as hora_t

Reloj = Callable[[], float]


def formatear(segundos: float, centesimas: bool = False) -> str:
    """``3725.5`` → ``"01:02:05"`` (o ``"01:02:05.50"`` con centésimas)."""
    signo = "-" if segundos < 0 else ""
    total_cs = round(abs(segundos) * 100)
    h, resto = divmod(total_cs, 360000)
    m, resto = divmod(resto, 6000)
    s, cs = divmod(resto, 100)
    base = f"{signo}{h:02d}:{m:02d}:{s:02d}"
    return f"{base}.{cs:02d}" if centesimas else base


def parsear_duracion(texto: str) -> float:
    """Acepta ``"90"`` (segundos), ``"05:00"``, ``"1:02:03"`` o ``"1h 30m 15s"``."""
    t = texto.strip().lower().replace(" ", "")
    if not t:
        raise ValueError("duración vacía")
    if re.fullmatch(r"\d+(\.\d+)?", t):
        segundos = float(t)
    elif re.fullmatch(r"\d+(:\d{1,2}){1,2}", t):
        partes = [int(p) for p in t.split(":")]
        if any(p >= 60 for p in partes[1:]):
            raise ValueError("minutos y segundos deben ser < 60")
        segundos = 0.0
        for p in partes:
            segundos = segundos * 60 + p
    elif (m := re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", t)) and any(m.groups()):
        h, mi, s = (int(g or 0) for g in m.groups())
        segundos = float(h * 3600 + mi * 60 + s)
    else:
        raise ValueError(f"formato de duración no reconocido: {texto!r}")
    if segundos <= 0 or segundos > 100 * 3600:
        raise ValueError("la duración debe estar entre 1 s y 100 h")
    return segundos


# ---------------------------------------------------------------- cronómetro
@dataclass
class Cronometro:
    """Cronómetro con pausas y vueltas. Guarda el tiempo acumulado de los tramos cerrados más
    el inicio del tramo actual, en vez de sumar 'ticks', así no acumula error aunque la
    GUI se retrase.
    """
    reloj: Reloj = time.monotonic
    _acumulado: float = 0.0           # tiempo de tramos anteriores (antes de pausar)
    _inicio: float | None = None      # instante del tramo actual; None = pausado
    vueltas: list[float] = field(default_factory=list)  # tiempos parciales de cada vuelta

    @property
    def corriendo(self) -> bool:
        """True si está contando (no pausado)."""
        return self._inicio is not None

    def transcurrido(self) -> float:
        """Tiempo total: tramos anteriores + lo que va del tramo actual."""
        extra = self.reloj() - self._inicio if self._inicio is not None else 0.0
        return self._acumulado + extra

    def iniciar(self) -> None:
        """Empieza o continúa; llamarlo estando en marcha no hace nada (idempotente)."""
        if self._inicio is None:
            self._inicio = self.reloj()

    def pausar(self) -> None:
        """Cierra el tramo actual sumándolo al acumulado."""
        if self._inicio is not None:
            self._acumulado += self.reloj() - self._inicio
            self._inicio = None

    def reiniciar(self) -> None:
        """Todo a cero, pausado y sin vueltas."""
        self._acumulado, self._inicio, self.vueltas = 0.0, None, []

    def vuelta(self) -> float:
        """Registra una vuelta y devuelve su duración parcial."""
        if not self.corriendo:
            raise RuntimeError("el cronómetro está detenido")
        parcial = self.transcurrido() - sum(self.vueltas)
        self.vueltas.append(parcial)
        return parcial

    def mejor_y_peor(self) -> tuple[int, int] | None:
        """Índices de la vuelta más rápida y más lenta (si hay al menos 2)."""
        if len(self.vueltas) < 2:
            return None
        return self.vueltas.index(min(self.vueltas)), self.vueltas.index(max(self.vueltas))


# ---------------------------------------------------------------- temporizador
@dataclass
class Temporizador:
    """Cuenta regresiva que se puede pausar. :meth:`comprobar` avisa una sola vez al terminar."""

    duracion: float
    reloj: Reloj = time.monotonic
    _crono: Cronometro = field(init=False)
    _avisado: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        """Valida que la duración sea positiva; internamente usa un Cronometro para medir lo
        transcurrido.
        """
        if self.duracion <= 0:
            raise ValueError("duración debe ser positiva")
        self._crono = Cronometro(self.reloj)

    def iniciar(self) -> None:
        """Arranca o continúa, salvo que ya haya terminado."""
        if not self.terminado:
            self._crono.iniciar()

    def pausar(self) -> None:
        """Pausa la cuenta regresiva."""
        self._crono.pausar()

    def reiniciar(self, duracion: float | None = None) -> None:
        """Vuelve a la duración completa (opcionalmente una nueva) y rearma el aviso."""
        if duracion is not None:
            self.duracion = duracion
        self._crono.reiniciar()
        self._avisado = False

    @property
    def corriendo(self) -> bool:
        """True si está contando y aún le queda tiempo."""
        return self._crono.corriendo and not self.terminado

    def restante(self) -> float:
        """Segundos que faltan; nunca negativo."""
        return max(0.0, self.duracion - self._crono.transcurrido())

    @property
    def terminado(self) -> bool:
        """True cuando llegó a 0."""
        return self.restante() == 0.0

    def progreso(self) -> float:
        """Fracción completada, de 0.0 a 1.0 (para la barra)."""
        return 1 - self.restante() / self.duracion

    def comprobar(self) -> bool:
        """True exactamente una vez: cuando se detecta el fin (para sonar la alarma)."""
        if self.terminado and not self._avisado:
            self._avisado = True
            self._crono.pausar()
            return True
        return False


# ---------------------------------------------------------------- alarmas
DIAS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")


@dataclass
class Alarma:
    """Alarma a una hora del día, opcionalmente solo ciertos días de la semana.

    ``dias`` vacío = todos los días. Se dispara como mucho una vez por día y
    admite posponer (*snooze*).
    """

    hora: hora_t
    etiqueta: str = ""
    dias: frozenset[int] = frozenset()   # 0 = lunes … 6 = domingo
    activa: bool = True
    _ultimo_dia: date | None = None
    _pospuesta_hasta: datetime | None = None

    @classmethod
    def desde_texto(cls, texto: str, etiqueta: str = "", dias: frozenset[int] = frozenset()) -> "Alarma":
        """Crea una alarma desde 'HH:MM' validando rangos (00:00 a 23:59)."""
        m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", texto)
        if not m or int(m[1]) > 23 or int(m[2]) > 59:
            raise ValueError("hora inválida, usá HH:MM (00:00-23:59)")
        return cls(hora_t(int(m[1]), int(m[2])), etiqueta, dias)

    def _aplica(self, dia: date) -> bool:
        """True si la alarma suena ese día (sin días configurados = todos los días). weekday():
        lunes=0.
        """
        return not self.dias or dia.weekday() in self.dias

    def proxima(self, ahora: datetime) -> datetime | None:
        """Próximo disparo a partir de ``ahora`` (incluida la posposición)."""
        if not self.activa:
            return None
        if self._pospuesta_hasta and self._pospuesta_hasta > ahora:
            return self._pospuesta_hasta
        for i in range(8):
            dia = ahora.date() + timedelta(days=i)
            momento = datetime.combine(dia, self.hora)
            if self._aplica(dia) and momento > ahora and dia != self._ultimo_dia:
                return momento
        return None

    def debe_sonar(self, ahora: datetime) -> bool:
        """Comprobación periódica: True una vez cuando llega la hora (o fin del snooze).

        Se tolera un retraso de hasta 60 s (p. ej. si el equipo estuvo
        suspendido un momento) para no perder la alarma.
        """
        if not self.activa:
            return False
        if self._pospuesta_hasta and ahora >= self._pospuesta_hasta:
            self._pospuesta_hasta = None
            return True
        objetivo = datetime.combine(ahora.date(), self.hora)
        if (self._aplica(ahora.date()) and self._ultimo_dia != ahora.date()
                and timedelta(0) <= ahora - objetivo <= timedelta(seconds=60)):
            self._ultimo_dia = ahora.date()
            return True
        return False

    def posponer(self, ahora: datetime, minutos: int = 5) -> datetime:
        """Snooze: vuelve a sonar dentro de ``minutos``. Devuelve el nuevo instante."""
        self._pospuesta_hasta = ahora + timedelta(minutes=minutos)
        return self._pospuesta_hasta

    def descripcion(self) -> str:
        """Texto para la lista: '07:00 Trabajo (lun, mié)' y '[off]' si está desactivada."""
        dias = "todos los días" if not self.dias else ", ".join(DIAS[d] for d in sorted(self.dias))
        return f"{self.hora:%H:%M} {self.etiqueta} ({dias}){'' if self.activa else ' [off]'}".replace("  ", " ")
