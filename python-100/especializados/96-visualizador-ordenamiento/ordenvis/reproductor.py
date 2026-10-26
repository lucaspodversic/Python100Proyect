"""Control de la animación, independiente de Tk.

:class:`Reproductor` envuelve un generador de pasos y mantiene su propia copia
del arreglo, más contadores y el estado de resaltado de cada barra. La GUI solo
llama a :meth:`avanzar` periódicamente y dibuja :attr:`valores` y :attr:`marcas`.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .algoritmos import ALGORITMOS, Paso, aplicar


def arreglo_aleatorio(n: int, semilla: int | None = None, modo: str = "aleatorio") -> list[int]:
    """Valores 1..n en distintos órdenes iniciales: aleatorio, casi, invertido, pocos (muchos repetidos)."""
    if n < 1:
        raise ValueError("n debe ser positivo")
    rng = random.Random(semilla)
    base = list(range(1, n + 1))
    if modo == "aleatorio":
        rng.shuffle(base)
    elif modo == "casi":
        for _ in range(max(1, n // 10)):
            i, j = rng.randrange(n), rng.randrange(n)
            base[i], base[j] = base[j], base[i]
    elif modo == "invertido":
        base.reverse()
    elif modo == "pocos":
        base = [rng.choice([n // 4 or 1, n // 2 or 1, 3 * n // 4 or 1, n]) for _ in range(n)]
    else:
        raise ValueError(f"modo desconocido: {modo}")
    return base


@dataclass
class Estadisticas:
    """Contadores de operaciones, para comparar algoritmos en números además de visualmente."""
    comparaciones: int = 0
    intercambios: int = 0
    escrituras: int = 0

    @property
    def pasos(self) -> int:
        """Total de operaciones (las marcas de 'ordenado' no cuentan porque no son trabajo del
        algoritmo).
        """
        return self.comparaciones + self.intercambios + self.escrituras


@dataclass
class Reproductor:
    """Reproduce paso a paso un algoritmo sobre una copia del arreglo: aplica cada Paso a
    ``valores``, recuerda qué índices resaltar, cuáles ya están ordenados y lleva las
    estadísticas. Es independiente de Tk, así que se testea sin pantalla.
    """
    inicial: list[int]
    algoritmo: str = "Burbuja"
    valores: list[int] = field(init=False)
    stats: Estadisticas = field(init=False, default_factory=Estadisticas)
    activos: tuple[int, ...] = field(init=False, default=())   # índices resaltados en el último paso
    tipo_activo: str = field(init=False, default="")
    ordenados: set[int] = field(init=False, default_factory=set)
    terminado: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        """Valida el nombre del algoritmo y deja todo en el estado inicial."""
        if self.algoritmo not in ALGORITMOS:
            raise ValueError(f"algoritmo desconocido: {self.algoritmo}")
        self.reiniciar()

    def reiniciar(self) -> None:
        """Vuelve al arreglo original con un generador nuevo y estadísticas en cero."""
        self.valores = list(self.inicial)
        # El generador trabaja sobre SU copia; nosotros reaplicamos los pasos en la nuestra,
        # lo que además valida que los pasos describan fielmente lo que hace el algoritmo.
        self._gen = ALGORITMOS[self.algoritmo](list(self.inicial))
        self.stats = Estadisticas()
        self.activos, self.tipo_activo, self.ordenados, self.terminado = (), "", set(), False

    def avanzar(self, n: int = 1) -> list[Paso]:
        """Avanza hasta ``n`` pasos; devuelve los aplicados. Marca ``terminado`` al agotarse."""
        hechos: list[Paso] = []
        for _ in range(n):
            try:
                p = next(self._gen)
            except StopIteration:
                self.terminado, self.activos, self.tipo_activo = True, (), ""
                break
            aplicar(self.valores, p)
            if p.tipo == "comparar":
                self.stats.comparaciones += 1
            elif p.tipo == "intercambiar":
                self.stats.intercambios += 1
            elif p.tipo == "escribir":
                self.stats.escrituras += 1
            else:
                self.ordenados.add(p.i)
            self.activos = (p.i,) if p.j < 0 else (p.i, p.j)
            self.tipo_activo = p.tipo
            hechos.append(p)
        return hechos

    def completar(self) -> None:
        """Avanza hasta el final (en bloques de 10 000 pasos)."""
        while not self.terminado:
            self.avanzar(10_000)
