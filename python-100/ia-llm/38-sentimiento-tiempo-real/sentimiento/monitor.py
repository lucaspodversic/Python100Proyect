"""Ventana deslizante temporal, métricas y alertas con período de enfriamiento."""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sentimiento.analizador import clasificar
from sentimiento.fuentes import FuenteFeed, Publicacion
from sentimiento.llm import ProveedorLLM


@dataclass
class Alerta:
    momento: datetime
    proporcion_negativa: float
    muestras: int
    ejemplos: list[str]


@dataclass
class Monitor:
    fuentes: list[FuenteFeed]
    consulta: str
    llm: ProveedorLLM | None = None
    ventana: timedelta = timedelta(minutes=15)
    umbral_negativo: float = 0.5       # alerta si > 50% negativo...
    minimo_muestras: int = 5           # ...con al menos 5 publicaciones (evita falsas alarmas)
    enfriamiento: timedelta = timedelta(minutes=10)
    _ventana: deque = field(default_factory=deque)   # (fecha, id, etiqueta, score, texto)
    # Ids ya procesados: evita contar dos veces lo que una fuente repite.
    # (Crece sin límite; para producción convendría acotarlo por tiempo.)
    _vistos: set[str] = field(default_factory=set)
    _ultima_alerta: datetime | None = None
    alertas: list[Alerta] = field(default_factory=list)

    def ciclo(self, ahora: datetime) -> Alerta | None:
        """Un sondeo: trae de todas las fuentes, deduplica, clasifica, actualiza ventana y evalúa alerta."""
        nuevas: list[Publicacion] = []
        for f in self.fuentes:
            try:
                nuevas += [p for p in f.obtener(self.consulta) if p.id not in self._vistos]
            except Exception:  # una fuente caída no debe frenar el monitor
                continue
        for p in nuevas:
            self._vistos.add(p.id)
        # Solo se clasifican las nuevas: lo ya visto conserva su etiqueta.
        etiquetas = clasificar(nuevas, self.llm)
        # Se insertan en orden cronológico para que el descarte por la izquierda
        # (las más viejas primero) sea correcto.
        for p in sorted(nuevas, key=lambda p: p.fecha):
            e, s = etiquetas[p.id]
            self._ventana.append((p.fecha, p.id, e, s, p.texto))
        # Descartar lo que quedó fuera de la ventana temporal
        while self._ventana and self._ventana[0][0] < ahora - self.ventana:
            self._ventana.popleft()
        return self._evaluar(ahora)

    def metricas(self) -> dict:
        n = len(self._ventana)
        conteo = Counter(x[2] for x in self._ventana)
        return {"muestras": n, **{k: conteo.get(k, 0) for k in ("positivo", "negativo", "neutral")},
                "score_medio": round(sum(x[3] for x in self._ventana) / n, 2) if n else 0.0}

    def _evaluar(self, ahora: datetime) -> Alerta | None:
        m = self.metricas()
        # Con pocas muestras una proporción alta es ruido (1 de 1 = 100%).
        if m["muestras"] < self.minimo_muestras:
            return None
        prop = m["negativo"] / m["muestras"]
        # Estrictamente mayor al umbral: exactamente 50% no alerta.
        if prop <= self.umbral_negativo:
            return None
        if self._ultima_alerta and ahora - self._ultima_alerta < self.enfriamiento:
            return None   # no repetir la misma alerta cada ciclo
        self._ultima_alerta = ahora
        # Se adjuntan los 3 ejemplos negativos más recientes para dar contexto.
        alerta = Alerta(ahora, round(prop, 2), m["muestras"], [x[4] for x in self._ventana if x[2] == "negativo"][-3:])
        self.alertas.append(alerta)
        return alerta
