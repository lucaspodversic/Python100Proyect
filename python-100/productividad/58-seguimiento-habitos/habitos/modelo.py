"""Modelo y cálculos puros.

Un hábito puede programarse para ciertos días de la semana
(p. ej. gimnasio lun/mié/vie). Los días no programados NO cortan la
racha: sólo cuentan los días en que tocaba cumplir.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

TODOS_LOS_DIAS = frozenset(range(7))  # 0 = lunes … 6 = domingo


@dataclass
class Habito:
    """Un hábito: fecha de creación, días programados y días cumplidos."""
    nombre: str
    creado: date
    dias_semana: frozenset[int] = TODOS_LOS_DIAS
    hechos: set[date] = field(default_factory=set)

    def toca(self, d: date) -> bool:
        # Antes de la creación nunca "tocaba": no cuenta como incumplido.
        return d.weekday() in self.dias_semana and d >= self.creado

    def marcar(self, d: date) -> None:
        # Caso borde: marcar antes de crear el hábito no tiene sentido.
        if d < self.creado:
            raise ValueError("No se puede marcar antes de la creación del hábito")
        self.hechos.add(d)

    def desmarcar(self, d: date) -> None:
        # discard (no remove): desmarcar un día no marcado no es error.
        self.hechos.discard(d)


@dataclass(frozen=True)
class Estadisticas:
    """Resultados de los cálculos sobre un hábito."""
    racha_actual: int
    mejor_racha: int
    cumplimiento: float  # 0..1 sobre los días programados de la ventana
    total: int


def _dias_programados(h: Habito, desde: date, hasta: date) -> list[date]:
    """Días entre `desde` y `hasta` (ambos incluidos) en que tocaba cumplir."""
    n = (hasta - desde).days
    return [desde + timedelta(i) for i in range(n + 1) if h.toca(desde + timedelta(i))]


def estadisticas(h: Habito, hoy: date, ventana: int = 30) -> Estadisticas:
    """Racha actual, mejor racha, cumplimiento en la ventana y total de días hechos."""
    programados = _dias_programados(h, h.creado, hoy)
    # Mejor racha: recorrido lineal de los días programados
    mejor = actual = 0
    for d in programados:
        # Un día programado sin cumplir reinicia la racha en curso.
        actual = actual + 1 if d in h.hechos else 0
        mejor = max(mejor, actual)
    # Racha actual: desde el final hacia atrás. Si hoy toca y aún no se
    # hizo, no se rompe la racha (el día no terminó).
    racha = 0
    for d in reversed(programados):
        if d in h.hechos:
            racha += 1
        # Hoy todavía puede cumplirse: se saltea sin cortar.
        elif d == hoy:
            continue
        else:
            break
    # Ventana de `ventana` días que termina hoy (sin ir antes de la creación).
    desde = max(h.creado, hoy - timedelta(days=ventana - 1))
    vent = _dias_programados(h, desde, hoy)
    # sum de booleanos = cantidad cumplida; sin días programados en la ventana → 0.
    cumpl = sum(d in h.hechos for d in vent) / len(vent) if vent else 0.0
    return Estadisticas(racha, mejor, cumpl, len(h.hechos))


def calendario(h: Habito, hoy: date, semanas: int = 4) -> str:
    """Mapa tipo GitHub: filas = días de la semana, columnas = semanas.

    '█' hecho, '·' pendiente/no hecho, ' ' no programado o futuro.
    """
    # Lunes de la semana más vieja que se muestra.
    inicio = hoy - timedelta(days=hoy.weekday() + 7 * (semanas - 1))
    etiquetas = "LMXJVSD"
    filas = []
    for dia in range(7):
        celdas = []
        for s in range(semanas):
            # Columna s = semana, fila dia = día de la semana.
            d = inicio + timedelta(days=7 * s + dia)
            celdas.append(" " if d > hoy or not h.toca(d) else ("█" if d in h.hechos else "·"))
        filas.append(f"{etiquetas[dia]} " + " ".join(celdas))
    return "\n".join(filas)
