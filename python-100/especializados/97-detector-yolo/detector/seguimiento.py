"""Seguimiento simple por IoU entre cuadros y conteo de cruces de una línea.

Para video: a cada cuadro se le pasan sus detecciones; el rastreador asocia
cada una con la pista existente de igual clase con mayor IoU (si supera
``umbral_iou``), crea pistas nuevas para las restantes y elimina las que no se
ven hace más de ``max_perdidos`` cuadros. Es la idea base de SORT, sin filtro
de Kalman.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .modelo import Caja, Deteccion
from .postproceso import iou


@dataclass
class Pista:
    """Un objeto seguido entre cuadros: id estable, clase, última caja, cuadros seguidos sin
    verlo e historial de centros.
    """
    id: int
    clase: str
    caja: Caja
    perdidos: int = 0
    historial: list[tuple[float, float]] = field(default_factory=list)


class Rastreador:
    """Seguimiento simple por IoU (estilo SORT sin filtro de Kalman): cada detección se asocia
    a la pista de la misma clase con la que más se superpone. Las no asociadas abren
    pistas nuevas y las pistas sin detección se borran tras ``max_perdidos`` cuadros.
    Opcionalmente cuenta cruces de una línea horizontal.
    """
    def __init__(self, umbral_iou: float = 0.3, max_perdidos: int = 5, linea_y: float | None = None) -> None:
        """``umbral_iou``: superposición mínima para considerar que es el mismo objeto.
        ``linea_y``: línea de conteo (None = no contar).
        """
        self.umbral_iou, self.max_perdidos, self.linea_y = umbral_iou, max_perdidos, linea_y
        self.pistas: dict[int, Pista] = {}
        self._sig = 1
        self.cruces: dict[str, int] = {"bajando": 0, "subiendo": 0}

    def actualizar(self, dets: list[Deteccion]) -> list[Pista]:
        """Procesa un cuadro y devuelve las pistas vistas en él. La asociación es voraz:
        primero los pares con más IoU, cada pista y cada detección se usan una sola
        vez. Los ids nunca se reutilizan.
        """
        # Pares candidatos ordenados por IoU descendente → asignación voraz 1 a 1.
        pares = sorted(((iou(p.caja, d.caja), pid, k) for pid, p in self.pistas.items()
                        for k, d in enumerate(dets) if p.clase == d.clase), reverse=True)
        usadas_p, usadas_d = set(), set()
        for v, pid, k in pares:
            if v < self.umbral_iou or pid in usadas_p or k in usadas_d:
                continue
            usadas_p.add(pid)
            usadas_d.add(k)
            self._mover(self.pistas[pid], dets[k].caja)
        for pid, p in list(self.pistas.items()):
            if pid not in usadas_p:
                p.perdidos += 1
                if p.perdidos > self.max_perdidos:
                    del self.pistas[pid]
        for k, d in enumerate(dets):
            if k not in usadas_d:
                self.pistas[self._sig] = Pista(self._sig, d.clase, d.caja, historial=[d.caja.centro])
                self._sig += 1
        return [p for p in self.pistas.values() if p.perdidos == 0]

    def _mover(self, p: Pista, caja: Caja) -> None:
        """Actualiza la pista con su nueva caja y cuenta un cruce si el centro pasó de un lado
        al otro de la línea. Las desigualdades asimétricas (< y <=) evitan contar
        dos veces un centro que cae justo sobre la línea.
        """
        y_antes = p.caja.centro[1]
        p.caja, p.perdidos = caja, 0
        p.historial.append(caja.centro)
        y_ahora = caja.centro[1]
        if self.linea_y is not None:
            if y_antes < self.linea_y <= y_ahora:
                self.cruces["bajando"] += 1
            elif y_antes >= self.linea_y > y_ahora:
                self.cruces["subiendo"] += 1
