"""Modelos de filtrado colaborativo, implementados a mano con numpy.

1. ``BaselineSesgos``: ``r̂ = μ + b_u + b_i`` (media global + sesgo de usuario
   y de película, regularizados). Es la línea base a superar.
2. ``ItemKNN``: "a quienes les gustó X también les gustó Y". Similitud coseno
   *ajustada* (centrada por usuario) entre películas; la predicción es el
   promedio ponderado de los k vecinos que el usuario ya calificó, sobre el baseline.
3. ``FactorizacionMatricial``: ``r̂ = μ + b_u + b_i + p_u·q_i`` entrenado por
   SGD (estilo Funk-SVD de la competencia Netflix).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .datos import Calificaciones


@dataclass
class BaselineSesgos:
    # reg actúa como "votos ficticios" en 0: con pocas notas el sesgo se encoge hacia 0.
    reg: float = 5.0
    mu: float = 0.0
    bu: np.ndarray = field(default_factory=lambda: np.zeros(0))
    bi: np.ndarray = field(default_factory=lambda: np.zeros(0))

    def ajustar(self, c: Calificaciones, iteraciones: int = 10) -> "BaselineSesgos":
        r = c.matriz
        visto = ~np.isnan(r)
        self.mu = float(np.nanmean(r))
        self.bu, self.bi = np.zeros(r.shape[0]), np.zeros(r.shape[1])
        # Desvío respecto de la media global; 0 en lo no visto para que no sume.
        res = np.where(visto, r - self.mu, 0.0)
        # Mínimos cuadrados alternados con regularización (forma cerrada).
        for _ in range(iteraciones):
            # b_i = Σ(r − μ − b_u) / (n_i + reg); luego b_u con los b_i nuevos. 10 vueltas bastan para converger.
            self.bi = (res - self.bu[:, None] * visto).sum(0) / (visto.sum(0) + self.reg)
            self.bu = (res - self.bi[None, :] * visto).sum(1) / (visto.sum(1) + self.reg)
        return self

    def base(self) -> np.ndarray:
        # Broadcasting: columna de sesgos de usuario + fila de sesgos de película → matriz completa.
        return self.mu + self.bu[:, None] + self.bi[None, :]

    def predecir_matriz(self) -> np.ndarray:
        # Recorte a la escala válida de notas.
        return np.clip(self.base(), 1, 5)


@dataclass
class ItemKNN:
    k: int = 15
    contraccion: float = 10.0  # "shrinkage": desconfía de similitudes con pocos usuarios en común
    baseline: BaselineSesgos = field(default_factory=BaselineSesgos)
    sim: np.ndarray = field(default_factory=lambda: np.zeros((0, 0)))
    _c: Calificaciones | None = None

    def ajustar(self, c: Calificaciones) -> "ItemKNN":
        self._c = c
        self.baseline.ajustar(c)
        visto = ~np.isnan(c.matriz)
        # Residuo respecto del baseline: quita "usuario generoso" y "película buena".
        res = np.where(visto, c.matriz - self.baseline.base(), 0.0)
        # Coseno entre columnas (películas) de la matriz de residuos; clip(1e-9) evita dividir por 0.
        norma = np.sqrt((res ** 2).sum(0))
        sim = (res.T @ res) / np.outer(norma, norma).clip(1e-9)
        # comunes[i, j] = usuarios que vieron ambas. Factor n / (n + 10): con 2 usuarios en común
        # la similitud se reduce a 1/6; con 100, apenas un 9%.
        comunes = visto.T.astype(float) @ visto.astype(float)
        sim *= comunes / (comunes + self.contraccion)
        # Una película no es vecina de sí misma.
        np.fill_diagonal(sim, 0.0)
        self.sim = sim
        return self

    def predecir_matriz(self) -> np.ndarray:
        assert self._c is not None
        r = self._c.matriz
        visto = ~np.isnan(r)
        base = self.baseline.base()
        res = np.where(visto, r - base, 0.0)
        # Sólo los k vecinos más similares de cada película (y con similitud positiva).
        sim = self.sim.copy()
        if self.k < sim.shape[0]:
            # k-ésima similitud más alta de cada fila (slice para conservar forma (n, 1) y hacer broadcasting).
            umbral = -np.sort(-sim, axis=1)[:, self.k - 1: self.k]
            sim[sim < umbral] = 0.0
        # Similitudes negativas se descartan: "no le gustó algo opuesto" es una señal débil y ruidosa.
        sim = sim.clip(0)
        num = res @ sim.T  # (usuarios, películas)
        # Denominador = suma de similitudes de los vecinos que el usuario SÍ vio.
        # np.divide con where: si no vio ningún vecino, el ajuste es 0 y queda el baseline.
        den = visto.astype(float) @ np.abs(sim.T)
        return np.clip(base + np.divide(num, den, out=np.zeros_like(num), where=den > 1e-9), 1, 5)

    def similares(self, pelicula: str, n: int = 5) -> list[tuple[str, float]]:
        assert self._c is not None
        i = self._c.idx_pelicula(pelicula)
        # Orden descendente por similitud (argsort del negativo).
        orden = np.argsort(-self.sim[i])[:n]
        return [(self._c.peliculas[j], float(self.sim[i, j])) for j in orden]


@dataclass
class FactorizacionMatricial:
    # 8 factores latentes alcanzan para 5 géneros; tasa y reg pequeños = SGD estable.
    factores: int = 8
    epocas: int = 60
    tasa: float = 0.01
    reg: float = 0.05
    semilla: int = 0
    mu: float = 0.0
    bu: np.ndarray = field(default_factory=lambda: np.zeros(0))
    bi: np.ndarray = field(default_factory=lambda: np.zeros(0))
    p: np.ndarray = field(default_factory=lambda: np.zeros((0, 0)))
    q: np.ndarray = field(default_factory=lambda: np.zeros((0, 0)))
    historial: list[float] = field(default_factory=list)

    def ajustar(self, c: Calificaciones) -> "FactorizacionMatricial":
        rng = np.random.default_rng(self.semilla)
        r = c.matriz
        us, its = np.nonzero(~np.isnan(r))
        notas = r[us, its]
        self.mu = float(notas.mean())
        self.bu, self.bi = np.zeros(r.shape[0]), np.zeros(r.shape[1])
        # Inicialización aleatoria pequeña (no ceros: con ceros los gradientes de p y q serían nulos).
        self.p = rng.normal(0, 0.1, (r.shape[0], self.factores))
        self.q = rng.normal(0, 0.1, (r.shape[1], self.factores))
        self.historial = []
        for _ in range(self.epocas):
            for n in rng.permutation(len(notas)):  # SGD: una calificación por paso
                u, i = us[n], its[n]
                e = notas[n] - (self.mu + self.bu[u] + self.bi[i] + self.p[u] @ self.q[i])
                self.bu[u] += self.tasa * (e - self.reg * self.bu[u])
                self.bi[i] += self.tasa * (e - self.reg * self.bi[i])
                # Copia: la actualización de q debe usar el p_u ANTERIOR, no el recién modificado.
                pu = self.p[u].copy()
                self.p[u] += self.tasa * (e * self.q[i] - self.reg * pu)
                self.q[i] += self.tasa * (e * pu - self.reg * self.q[i])
            pred = self.mu + self.bu[us] + self.bi[its] + (self.p[us] * self.q[its]).sum(1)
            # RMSE de entrenamiento por época, para verificar que el SGD converge.
            self.historial.append(float(np.sqrt(((notas - pred) ** 2).mean())))
        return self

    def predecir_matriz(self) -> np.ndarray:
        return np.clip(self.mu + self.bu[:, None] + self.bi[None, :] + self.p @ self.q.T, 1, 5)


def recomendar(modelo: BaselineSesgos | ItemKNN | FactorizacionMatricial, c: Calificaciones, usuario: str,
               n: int = 5) -> list[tuple[str, float]]:
    """Top-n películas NO vistas, por nota predicha."""
    u = c.idx_usuario(usuario)
    pred = modelo.predecir_matriz()[u].copy()
    # −inf en las ya vistas: quedan al final del orden y nunca se recomiendan.
    pred[~np.isnan(c.matriz[u])] = -np.inf
    orden = np.argsort(-pred)[:n]
    return [(c.peliculas[i], float(pred[i])) for i in orden]


def populares(c: Calificaciones, n: int = 5, m: float = 10.0) -> list[tuple[str, float]]:
    """Arranque en frío (usuario nuevo): promedio bayesiano.

    ``(v·R + m·C) / (v + m)``: v = votos, R = promedio de la película,
    C = promedio global. Evita que una película con un solo 5 encabece el ranking.
    """
    r = c.matriz
    v = (~np.isnan(r)).sum(0)
    # maximum(v, 1) evita la división por 0 en películas sin votos (luego se reemplaza por 0).
    prom = np.where(v > 0, np.nansum(r, 0) / np.maximum(v, 1), 0.0)
    global_ = float(np.nanmean(r))
    # m = 10 votos "virtuales" con la media global: hacen falta muchos votos para alejarse de ella.
    score = (v * prom + m * global_) / (v + m)
    orden = np.argsort(-score)[:n]
    return [(c.peliculas[i], float(score[i])) for i in orden]
