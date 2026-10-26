"""Sintaxis de consultas.

* ``palabra``: término opcional que suma relevancia (OR ponderado).
* ``+palabra``: obligatorio.
* ``-palabra``: excluye documentos que lo contengan.
* ``"frase exacta"``: obligatoria y adyacente, en orden.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .texto import terminos, tokens_con_posicion

_TOKEN = re.compile(r'([+-]?)"([^"]*)"|([+-]?)(\S+)')


@dataclass
class Consulta:
    """Consulta ya analizada: términos opcionales (suman puntaje), obligatorios (+término),
    excluidos (-término) y frases exactas entre comillas con la posición relativa de
    cada término.
    """
    opcionales: list[str] = field(default_factory=list)
    obligatorios: list[str] = field(default_factory=list)
    excluidos: list[str] = field(default_factory=list)
    # Cada frase: [(término, desplazamiento relativo)], p. ej. "base de datos" → [(bas,0),(dat,2)]
    frases: list[list[tuple[str, int]]] = field(default_factory=list)

    @property
    def vacia(self) -> bool:
        """True si no queda nada positivo para buscar (p. ej. solo stopwords o solo
        exclusiones).
        """
        return not (self.opcionales or self.obligatorios or self.frases)

    def positivos(self) -> list[str]:
        """Términos que puntúan (los de las frases también cuentan)."""
        return self.opcionales + self.obligatorios + [t for f in self.frases for t, _ in f]


def parsear(texto: str) -> Consulta:
    """Recorre la consulta con una regex que reconoce [+-]"frase" o [+-]palabra. Una frase de
    un solo término útil se trata como obligatorio y una frase excluida excluye todos
    sus términos. Los desplazamientos de frase son relativos al primer término y
    conservan los huecos que dejan las stopwords ('base de datos' → bas en 0, dat en 2).
    """
    c = Consulta()
    for m in _TOKEN.finditer(texto):
        if m.group(2) is not None:  # frase entre comillas
            tp = tokens_con_posicion(m.group(2))
            if m.group(1) == "-":
                c.excluidos.extend(t for t, _ in tp)
            elif len(tp) > 1:
                base = tp[0][1]
                c.frases.append([(t, p - base) for t, p in tp])
            elif tp:
                c.obligatorios.append(tp[0][0])
            continue
        signo, ts = m.group(3), terminos(m.group(4))
        destino = {"+": c.obligatorios, "-": c.excluidos}.get(signo, c.opcionales)
        destino.extend(ts)
    return c
