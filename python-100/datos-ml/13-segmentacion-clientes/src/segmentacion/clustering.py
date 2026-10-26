"""K-Means sobre RFM transformado + perfilado y nombres de segmento.

Por qué la transformación: RFM es muy asimétrico (pocos clientes gastan
muchísimo). ``log1p`` + ``StandardScaler`` evita que K-Means (distancia
euclídea) quede dominado por el monetario.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

# Campaña sugerida por nombre de segmento.
CAMPAÑAS = {
    "Campeones": "Programa VIP, acceso anticipado, pedir reseñas/referidos",
    "Leales": "Puntos por frecuencia, upselling a productos premium",
    "Potenciales": "Bienvenida + recomendaciones personalizadas para 2ª/3ª compra",
    "Dormidos": "Campaña de reactivación con cupón por tiempo limitado",
}


def _transformar(rfm: pd.DataFrame) -> np.ndarray:
    # log1p(x) = log(1 + x): admite 0 (recencia del mismo día) sin dar -inf.
    return np.log1p(rfm[["recencia", "frecuencia", "monetario"]].to_numpy(dtype=float))


def elegir_k(rfm: pd.DataFrame, k_min: int = 3, k_max: int = 8, semilla: int = 0) -> tuple[int, dict[int, float]]:
    """Elige k por coeficiente de silueta (mayor = clusters más separados).

    ``k_min=3`` por defecto: la silueta suele favorecer k=2 ("compran / no
    compran"), que es poco accionable para marketing. Conviene mirar también
    la tabla de puntajes y el criterio de negocio, no sólo el máximo.
    """
    # Mismo preprocesamiento que Segmentador.ajustar, para que la silueta evalúe el mismo espacio.
    x = StandardScaler().fit_transform(_transformar(rfm))
    puntajes = {k: float(silhouette_score(x, KMeans(k, n_init=10, random_state=semilla).fit_predict(x)))
                # La silueta exige k ≤ n−1; con pocos clientes se recorta el rango.
                # n_init=10: K-Means se reinicia 10 veces y se queda con la mejor inercia (evita mínimos locales).
                for k in range(k_min, min(k_max, len(rfm) - 1) + 1)}
    # Se devuelve el k ganador y todos los puntajes para que la persona pueda decidir.
    return max(puntajes, key=puntajes.__getitem__), puntajes


@dataclass
class Segmentador:
    k: int = 4
    semilla: int = 0
    # El escalador se guarda para aplicar exactamente la misma transformación a clientes nuevos (asignar).
    escalador: StandardScaler = field(default_factory=StandardScaler)
    modelo: KMeans | None = None
    nombres: dict[int, str] = field(default_factory=dict)

    def ajustar(self, rfm: pd.DataFrame) -> pd.DataFrame:
        x = self.escalador.fit_transform(_transformar(rfm))
        self.modelo = KMeans(self.k, n_init=10, random_state=self.semilla).fit(x)
        res = rfm.assign(cluster=self.modelo.labels_)
        # Los números de cluster de K-Means son arbitrarios; se traducen a nombres de negocio por su perfil.
        self.nombres = self._nombrar(res)
        # La lambda en campaña se evalúa después de crear "segmento" (assign procesa en orden).
        return res.assign(segmento=res["cluster"].map(self.nombres), campaña=lambda d: d["segmento"].map(CAMPAÑAS))

    def asignar(self, rfm: pd.DataFrame) -> pd.Series:
        """Asigna clientes nuevos a los segmentos ya aprendidos."""
        assert self.modelo is not None, "llamar a ajustar() primero"
        # transform (no fit_transform): se reutilizan media y desvío aprendidos en ajustar.
        etiquetas = self.modelo.predict(self.escalador.transform(_transformar(rfm)))
        return pd.Series(etiquetas, index=rfm.index).map(self.nombres)

    @staticmethod
    def _nombrar(res: pd.DataFrame) -> dict[int, str]:
        """Nombra clusters por puntaje: (−recencia, +frecuencia, +monetario) en rangos.

        - Puntaje más alto => "Campeones".
        - El de mayor recencia (más tiempo sin comprar) => "Dormidos".
        - Entre los restantes, el más frecuente => "Leales", y el resto "Potenciales".
        Con k > 4 los clusters extra se numeran ("Potenciales 2", ...).
        """
        # Mediana en lugar de media: robusta ante unos pocos clientes con gasto extremo.
        perfil = res.groupby("cluster")[["recencia", "frecuencia", "monetario"]].median()
        # Suma de rangos (1..k) por variable: compara clusters sin importar las escalas.
        # Recencia con signo negativo porque menos días sin comprar es mejor.
        puntaje = (-perfil["recencia"]).rank() + perfil["frecuencia"].rank() + perfil["monetario"].rank()
        nombres: dict[int, str] = {}
        campeon = int(puntaje.idxmax())
        nombres[campeon] = "Campeones"
        # Cada `if len(resto)` protege el caso k pequeño (p. ej. k=2 no llega a tener "Leales").
        resto = perfil.drop(index=campeon)
        if len(resto):
            dormido = int(resto["recencia"].idxmax())
            nombres[dormido] = "Dormidos"
            resto = resto.drop(index=dormido)
        if len(resto):
            leal = int(resto["frecuencia"].idxmax())
            nombres[leal] = "Leales"
            resto = resto.drop(index=leal)
        # El primero sobrante es "Potenciales" y los demás "Potenciales 2", "Potenciales 3", ...
        for i, c in enumerate(resto.index, start=1):
            nombres[int(c)] = "Potenciales" if i == 1 else f"Potenciales {i}"
        return nombres

    @staticmethod
    def resumen(res: pd.DataFrame) -> pd.DataFrame:
        """Tabla para el equipo de marketing: tamaño y medianas por segmento."""
        # Ordenado por gasto total: arriba el segmento que más factura.
        return (res.groupby("segmento")
                .agg(clientes=("recencia", "size"), recencia_med=("recencia", "median"),
                     frecuencia_med=("frecuencia", "median"), gasto_med=("monetario", "median"),
                     gasto_total=("monetario", "sum"))
                .sort_values("gasto_total", ascending=False))
