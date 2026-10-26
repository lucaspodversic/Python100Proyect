"""Carga y normalización del CSV de movimientos.

Acepta exportaciones típicas de home banking:
- separador ``,`` o ``;`` (detectado automáticamente);
- montos con coma decimal (``-1.234,56``) o punto (``-1234.56``);
- un único ``monto`` con signo, o dos columnas ``debito``/``credito``;
- fechas ``dd/mm/aaaa`` o ``aaaa-mm-dd``.

Si falta la columna ``categoria`` se infiere por palabras clave.
"""

from __future__ import annotations

import io
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

# Palabras clave en minúsculas y sin tildes; se evalúan en orden y gana la primera categoría que coincide.
# "dia " y "bar " llevan espacio para no coincidir con "diario" o "barbería".
REGLAS_CATEGORIA: dict[str, list[str]] = {
    "Sueldo": ["sueldo", "haberes", "salario", "nomina"],
    "Supermercado": ["coto", "carrefour", "dia ", "jumbo", "disco", "supermercado", "chino"],
    "Vivienda": ["alquiler", "expensas", "abl", "hipoteca"],
    "Servicios": ["edenor", "edesur", "metrogas", "aysa", "telecentro", "fibertel", "personal", "movistar", "claro"],
    "Transporte": ["sube", "uber", "cabify", "ypf", "shell", "axion", "peaje", "nafta"],
    "Salidas": ["restaurante", "bar ", "rappi", "pedidosya", "cine", "cerveceria"],
    "Suscripciones": ["netflix", "spotify", "disney", "youtube", "icloud", "chatgpt"],
    "Salud": ["farmacia", "osde", "swiss medical", "galeno", "medico"],
    "Inversiones": ["plazo fijo", "fci", "cedear", "dolar mep"],
}


def _sin_tildes(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def categorizar(descripcion: str, monto: float) -> str:
    # Espacios al principio y al final: así "dia " también coincide si es la última palabra.
    d = f" {_sin_tildes(descripcion.lower())} "
    for cat, claves in REGLAS_CATEGORIA.items():
        if any(k in d for k in claves):
            return cat
    # Sin coincidencias, el signo del monto decide la categoría genérica.
    return "Otros ingresos" if monto > 0 else "Otros gastos"


def _a_numero(serie: pd.Series) -> pd.Series:
    """Convierte textos de montos a float detectando el separador decimal por fila."""
    def conv(v: object) -> float:
        if isinstance(v, (int, float, np.number)):
            return float(v)  # type: ignore[arg-type]
        # Se quitan "$", espacios y letras; quedan dígitos, separadores y el signo.
        s = re.sub(r"[^\d,.\-]", "", str(v))
        if not s:
            return float("nan")
        # Si la última coma está después del último punto, la coma es decimal (estilo AR/ES).
        if "," in s and (s.rfind(",") > s.rfind(".")):
            s = s.replace(".", "").replace(",", ".")  # formato 1.234,56
        else:
            s = s.replace(",", "")  # formato 1,234.56
        return float(s)
    return serie.map(conv).astype(float)


def cargar_movimientos(origen: Path | str | io.StringIO) -> pd.DataFrame:
    texto = origen.getvalue() if isinstance(origen, io.StringIO) else Path(origen).read_text(encoding="utf-8-sig")
    # Detección del separador por la cabecera: el que más aparece en la primera línea.
    # utf-8-sig (al leer el archivo) quita el BOM que agrega Excel.
    sep = ";" if texto.splitlines()[0].count(";") > texto.splitlines()[0].count(",") else ","
    # Todo como texto: los montos se convierten luego con _a_numero (pandas no entiende "1.234,56").
    df = pd.read_csv(io.StringIO(texto), sep=sep, dtype=str)
    # Cabeceras normalizadas ("Débito" → "debito") y sinónimos de banco renombrados al nombre interno.
    df.columns = [_sin_tildes(c.strip().lower()) for c in df.columns]
    df = df.rename(columns={"descripción": "descripcion", "concepto": "descripcion", "detalle": "descripcion",
                            "importe": "monto", "debito": "debito", "credito": "credito"})
    if "monto" not in df.columns:
        if {"debito", "credito"} <= set(df.columns):
            # Formato débito/crédito: crédito suma y débito resta; la celda vacía cuenta como 0.
            df["monto"] = _a_numero(df["credito"].fillna("0")) - _a_numero(df["debito"].fillna("0"))
        else:
            raise ValueError("El CSV necesita 'monto' o 'debito'/'credito'")
    else:
        df["monto"] = _a_numero(df["monto"])
    if not {"fecha", "descripcion"} <= set(df.columns):
        raise ValueError("El CSV necesita las columnas 'fecha' y 'descripcion'")
    # Si TODAS las fechas son ISO se usa ese formato; si no, dd/mm/aaaa (evita confundir 03/04 con 4 de marzo).
    # errors="coerce": fechas inválidas → NaT y se descartan en dropna.
    iso = df["fecha"].str.match(r"^\d{4}-\d{2}-\d{2}")
    df["fecha"] = pd.to_datetime(df["fecha"], format="ISO8601" if iso.all() else "%d/%m/%Y", errors="coerce")
    df = df.dropna(subset=["fecha", "monto"])
    if "categoria" not in df.columns:
        df["categoria"] = [categorizar(d, m) for d, m in zip(df["descripcion"], df["monto"])]
    else:
        # Columna categoria presente pero con huecos: sólo se infieren las vacías; las del usuario se respetan.
        faltan = df["categoria"].isna() | (df["categoria"].str.strip() == "")
        df.loc[faltan, "categoria"] = [categorizar(d, m) for d, m in zip(df.loc[faltan, "descripcion"], df.loc[faltan, "monto"])]
    df["tipo"] = np.where(df["monto"] >= 0, "Ingreso", "Gasto")
    # Mes como texto "AAAA-MM": sirve de clave para agrupar y para el dropdown del dashboard.
    df["mes"] = df["fecha"].dt.to_period("M").astype(str)
    return df[["fecha", "mes", "descripcion", "categoria", "tipo", "monto"]].sort_values("fecha").reset_index(drop=True)


def generar_demo(meses: int = 6, semilla: int = 0, inicio: str = "2025-01-01") -> pd.DataFrame:
    """Movimientos ficticios realistas (sueldo, alquiler, súper, salidas...)."""
    rng = np.random.default_rng(semilla)
    filas = []
    # freq="MS" = primer día de cada mes. Gastos fijos en días fijos y variables con montos al azar.
    for m in pd.date_range(inicio, periods=meses, freq="MS"):
        filas += [(m + pd.Timedelta(days=1), "Haberes ACME SA", 1_500_000.0),
                  (m + pd.Timedelta(days=4), "Alquiler depto", -450_000.0),
                  (m + pd.Timedelta(days=9), "Expensas", -95_000.0),
                  (m + pd.Timedelta(days=11), "Edenor", -float(rng.integers(25, 60) * 1000)),
                  (m + pd.Timedelta(days=12), "Netflix", -12_000.0)]
        for _ in range(rng.integers(6, 10)):
            filas.append((m + pd.Timedelta(days=int(rng.integers(0, 27))), str(rng.choice(["Coto", "Carrefour", "Dia "])),
                          -float(rng.integers(15, 90) * 1000)))
        for _ in range(rng.integers(2, 6)):
            filas.append((m + pd.Timedelta(days=int(rng.integers(0, 27))), str(rng.choice(["Rappi", "Cerveceria", "Cine"])),
                          -float(rng.integers(8, 45) * 1000)))
        for _ in range(rng.integers(3, 7)):
            filas.append((m + pd.Timedelta(days=int(rng.integers(0, 27))), str(rng.choice(["Uber", "Carga SUBE", "YPF"])),
                          -float(rng.integers(5, 40) * 1000)))
        # Ingreso extra ocasional (50% de los meses) para que no todos los meses sean iguales.
        if rng.random() < 0.5:
            filas.append((m + pd.Timedelta(days=20), "Venta bici usada", float(rng.integers(50, 200) * 1000)))
    df = pd.DataFrame(filas, columns=["fecha", "descripcion", "monto"])
    # La demo pasa por el mismo cargar_movimientos que un CSV real: categorías y columnas idénticas.
    csv = df.assign(fecha=df["fecha"].dt.strftime("%Y-%m-%d")).to_csv(index=False)
    return cargar_movimientos(io.StringIO(csv))
