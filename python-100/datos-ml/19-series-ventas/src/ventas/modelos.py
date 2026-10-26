"""Modelos de pronóstico con interfaz común y *fallback* documentado.

Orden de preferencia en ``pronosticar(..., modelo="auto")``:

1. **SARIMA** (statsmodels ``SARIMAX``) con búsqueda chica de órdenes por AIC
   sobre log(ventas) — el log estabiliza la varianza de una serie multiplicativa.
2. Si SARIMA no es viable → **Holt-Winters** (``ExponentialSmoothing``).
3. Si nada de statsmodels es viable → **Naive estacional** (ŷ[t+h] = y[t+h-12]).

"No viable" significa: statsmodels no instalado, serie demasiado corta
(SARIMA estacional necesita ≥ 3 ciclos; Holt-Winters ≥ 2), valores no positivos
para el log, o que el ajuste lance una excepción / no converja a algo finito.
El motivo queda registrado en ``Pronostico.notas`` para que no sea silencioso.
"""

from __future__ import annotations

import itertools
import warnings
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
import pandas as pd

Z80 = 1.2816  # cuantil normal para un intervalo central del 80 %


@dataclass
# Resultado común de todos los modelos: media e intervalo del 80% con índice de fechas futuras.
class Pronostico:
    modelo: str
    media: pd.Series
    inferior: pd.Series
    superior: pd.Series
    notas: list[str] = field(default_factory=list)

    def como_tabla(self) -> pd.DataFrame:
        return pd.DataFrame({"pronostico": self.media, "inf_80": self.inferior, "sup_80": self.superior}).round(1)


# Protocol: cualquier clase con `nombre` y `ajustar_y_pronosticar` sirve (tipado estructural).
class Modelo(Protocol):
    nombre: str

    def ajustar_y_pronosticar(self, serie: pd.Series, horizonte: int) -> Pronostico: ...


class ModeloNoViable(RuntimeError):
    """El modelo no puede usarse con esta serie (se intenta el siguiente)."""


def _indice_futuro(serie: pd.Series, horizonte: int) -> pd.DatetimeIndex:
    # Frecuencia del índice (o inferida); si no se puede, se asume mensual.
    # Se generan horizonte+1 fechas desde la última observada y se descarta esa primera.
    frec = serie.index.freq or pd.infer_freq(serie.index) or "MS"
    return pd.date_range(serie.index[-1], periods=horizonte + 1, freq=frec)[1:]


class NaiveEstacional:
    """ŷ[t+h] = último valor observado de la misma estación. Siempre viable si hay ≥ 1 ciclo."""

    nombre = "naive_estacional"

    def __init__(self, periodo: int = 12) -> None:
        self.periodo = periodo

    def ajustar_y_pronosticar(self, serie: pd.Series, horizonte: int) -> Pronostico:
        m = self.periodo if len(serie) >= self.periodo else 1  # si ni un ciclo: naive simple
        # Último ciclo observado; se repite cíclicamente (h % m) para todo el horizonte.
        ultimo = serie.to_numpy()[-m:]
        media = np.array([ultimo[h % m] for h in range(horizonte)])
        # Escala del error: RMS de las diferencias estacionales (incluye el sesgo por tendencia,
        # que el naive ignora); crece con √(ciclos hacia adelante).
        dif = serie.diff(m).dropna()
        sigma = float(np.sqrt(np.mean(dif**2))) if len(dif) > 1 else float(serie.std() or 0)
        # k = número de ciclos hacia adelante (1 para los primeros 12 pasos, 2 para los siguientes…).
        k = np.arange(horizonte) // m + 1
        idx = _indice_futuro(serie, horizonte)
        return Pronostico(self.nombre, pd.Series(media, idx), pd.Series(media - Z80 * sigma * np.sqrt(k), idx),
                          pd.Series(media + Z80 * sigma * np.sqrt(k), idx))


class ModeloHoltWinters:
    nombre = "holt_winters"

    def __init__(self, periodo: int = 12) -> None:
        self.periodo = periodo

    def ajustar_y_pronosticar(self, serie: pd.Series, horizonte: int) -> Pronostico:
        # Con menos de 2 ciclos no se pueden estimar los factores estacionales de forma fiable.
        if len(serie) < 2 * self.periodo:
            raise ModeloNoViable(f"Holt-Winters necesita ≥ {2 * self.periodo} puntos (hay {len(serie)})")
        try:
            from statsmodels.tsa.holtwinters import ExponentialSmoothing
        except ImportError as e:  # pragma: no cover - depende del entorno
            raise ModeloNoViable("statsmodels no está instalado") from e
        # Estacionalidad multiplicativa sólo si todo es positivo (requisito del modelo); si no, aditiva.
        # Tendencia amortiguada (damped): evita extrapolar el crecimiento sin límite.
        estacional = "mul" if (serie > 0).all() else "add"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ajuste = ExponentialSmoothing(serie, trend="add", damped_trend=True, seasonal=estacional,
                                          seasonal_periods=self.periodo).fit()
        media = ajuste.forecast(horizonte)
        # Desvío de los residuos in-sample como escala del error de un paso.
        sigma = float(np.std(ajuste.resid))
        h = np.arange(1, horizonte + 1)
        banda = Z80 * sigma * np.sqrt(h)  # aproximación: varianza crece ~ lineal con h
        media.index = _indice_futuro(serie, horizonte)
        return Pronostico(self.nombre, media, media - banda, media + banda)


class ModeloSARIMA:
    """SARIMA(p,d,q)(P,D,Q,m) sobre log(y); elige órdenes por AIC en una grilla chica."""

    nombre = "sarima"

    def __init__(self, periodo: int = 12, grilla_pq: tuple[int, ...] = (0, 1), grilla_PQ: tuple[int, ...] = (0, 1)) -> None:
        self.periodo, self.grilla_pq, self.grilla_PQ = periodo, grilla_pq, grilla_PQ
        self.orden_elegido: tuple[tuple[int, int, int], tuple[int, int, int, int]] | None = None

    def ajustar_y_pronosticar(self, serie: pd.Series, horizonte: int) -> Pronostico:
        # SARIMA con D=1 consume un ciclo al diferenciar; hacen falta ≥ 3 ciclos (36 meses) para ajustar bien.
        if len(serie) < 3 * self.periodo:
            raise ModeloNoViable(f"SARIMA estacional necesita ≥ {3 * self.periodo} puntos (hay {len(serie)})")
        if (serie <= 0).any():
            raise ModeloNoViable("hay valores ≤ 0: no se puede aplicar log")
        try:
            from statsmodels.tsa.statespace.sarimax import SARIMAX
        except ImportError as e:  # pragma: no cover
            raise ModeloNoViable("statsmodels no está instalado") from e
        # Grilla: p, q, P, Q ∈ {0, 1} → 16 combinaciones; d = D = 1 (diferencia simple y estacional).
        y = np.log(serie)
        mejor: tuple[float, object, tuple] | None = None
        for p, q, P, Q in itertools.product(self.grilla_pq, self.grilla_pq, self.grilla_PQ, self.grilla_PQ):
            orden, est = (p, 1, q), (P, 1, Q, self.periodo)
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    r = SARIMAX(y, order=orden, seasonal_order=est).fit(disp=False)
            except Exception:  # noqa: BLE001 - un orden que falla simplemente se descarta
                continue
            # Se queda con el menor AIC (balance entre ajuste y cantidad de parámetros).
            if np.isfinite(r.aic) and (mejor is None or r.aic < mejor[0]):
                mejor = (r.aic, r, (orden, est))
        if mejor is None:
            raise ModeloNoViable("ningún orden SARIMA convergió")
        _, res, self.orden_elegido = mejor
        fc = res.get_forecast(horizonte)  # type: ignore[attr-defined]
        # alpha=0.2 → intervalo del 80%; se calcula en escala log y se transforma con exp (sigue siendo válido).
        ci = fc.conf_int(alpha=0.2)
        idx = _indice_futuro(serie, horizonte)
        # Volver de log: exp(media log) = mediana; es la estimación robusta habitual.
        media = pd.Series(np.exp(fc.predicted_mean.to_numpy()), idx)
        if not np.isfinite(media).all():
            raise ModeloNoViable("pronóstico no finito")
        return Pronostico(self.nombre, media, pd.Series(np.exp(ci.iloc[:, 0].to_numpy()), idx),
                          pd.Series(np.exp(ci.iloc[:, 1].to_numpy()), idx),
                          [f"orden elegido {self.orden_elegido} (AIC={mejor[0]:.1f})"])


# Nombre de CLI → clase, para --modelo sarima/holt_winters/naive.
MODELOS: dict[str, type] = {"sarima": ModeloSARIMA, "holt_winters": ModeloHoltWinters, "naive": NaiveEstacional}


def pronosticar(serie: pd.Series, horizonte: int = 12, modelo: str = "auto", periodo: int = 12,
                cadena: list[Modelo] | None = None) -> Pronostico:
    """Pronostica con el modelo pedido o con la cadena auto + fallback."""
    if horizonte < 1:
        raise ValueError("horizonte debe ser ≥ 1")
    # Se descartan NaN; con menos de 2 puntos ningún modelo tiene sentido.
    serie = serie.astype(float).dropna()
    if len(serie) < 2:
        raise ValueError("se necesitan al menos 2 observaciones")
    if cadena is None:
        if modelo == "auto":
            # auto: del más sofisticado al más simple; el naive estacional casi siempre es viable.
            cadena = [ModeloSARIMA(periodo), ModeloHoltWinters(periodo), NaiveEstacional(periodo)]
        else:
            cadena = [MODELOS[modelo](periodo)]
            # Un modelo pedido explícitamente también tiene el naive como red de seguridad.
            if modelo != "naive":
                cadena.append(NaiveEstacional(periodo))
    notas: list[str] = []
    for m in cadena:
        try:
            p = m.ajustar_y_pronosticar(serie, horizonte)
            # Las notas de los modelos descartados van primero, luego las del modelo que funcionó.
            p.notas = notas + p.notas
            return p
        except ModeloNoViable as e:
            notas.append(f"{m.nombre} descartado: {e}")
        except Exception as e:  # noqa: BLE001 - cualquier fallo inesperado activa el fallback
            notas.append(f"{m.nombre} falló ({type(e).__name__}: {e})")
    raise RuntimeError("ningún modelo pudo pronosticar: " + "; ".join(notas))
