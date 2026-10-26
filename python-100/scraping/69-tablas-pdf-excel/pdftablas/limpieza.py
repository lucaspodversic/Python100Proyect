"""Limpieza de tablas crudas: espacios, filas vacías, títulos, números y tablas partidas entre páginas."""
from __future__ import annotations

import re

from .extraer import Tabla

# "Parece número": signo opcional, dígitos con separadores/espacios y % opcional al final.
_NUM = re.compile(r"^[-+]?[\d.,\s]+%?$")


def convertir_numero(texto: str, decimal: str = ",") -> float | str:
    """'1.250,50' → 1250.5 (decimal=','), '1,250.50' → 1250.5 (decimal='.'), '15%' → 0.15.

    Si no parece número, devuelve el texto tal cual (p. ej. códigos con letras).
    """
    t = texto.strip()
    # Vacío, con letras ("A-12") o sólo separadores (",.") → se deja como texto.
    if not t or not _NUM.match(t) or not re.search(r"\d", t):
        return texto
    porciento = t.endswith("%")
    # Espacios como separador de miles ("1 250,50", estilo francés) también se quitan.
    t = t.rstrip("%").replace(" ", "")
    # El separador de miles es el opuesto al decimal elegido por el usuario
    # (no se adivina: "1.250" es ambiguo, depende del país del informe).
    miles = "." if decimal == "," else ","
    t = t.replace(miles, "").replace(decimal, ".")
    try:
        v = float(t)
    except ValueError:
        # Ej. "1,2,3" con decimal="," → "1.2.3": no es número, se conserva el original.
        return texto
    # Porcentajes como fracción: Excel los muestra bien con formato %.
    return v / 100 if porciento else v


def limpiar(tabla: Tabla, decimal: str = ",", numeros: bool = True, min_relleno: float = 0.5) -> Tabla:
    """1) normaliza espacios/saltos, 2) quita filas y columnas vacías,
    3) descarta filas iniciales poco llenas (títulos sobre la tabla),
    4) convierte números (sin tocar el encabezado)."""
    # 1) Celdas multilínea ("Uva\nroja") → una sola línea con espacios simples.
    filas = [[" ".join(str(c).split()) for c in f] for f in tabla.filas]
    # 2a) Filas totalmente vacías fuera.
    filas = [f for f in filas if any(f)]
    if not filas:
        return Tabla(tabla.pagina, tabla.indice, [])
    # Filas de distinto largo (pasa con celdas fusionadas) se rellenan hasta el ancho máximo.
    ancho = max(len(f) for f in filas)
    filas = [f + [""] * (ancho - len(f)) for f in filas]
    # 2b) Columnas vacías en todas las filas fuera (la estrategia "texto" suele crearlas).
    cols = [j for j in range(ancho) if any(f[j] for f in filas)]
    filas = [[f[j] for j in cols] for f in filas]
    # 3) Un título sobre la tabla ocupa 1 celda de N: si menos de la mitad está llena, se descarta.
    #    Se deja al menos una fila para no vaciar la tabla.
    while len(filas) > 1 and sum(1 for c in filas[0] if c) / len(filas[0]) < min_relleno:
        filas.pop(0)
    # 4) El encabezado queda como texto aunque sea numérico (ej. años "2025", "2026").
    if numeros:
        filas = [filas[0]] + [[convertir_numero(c, decimal) for c in f] for f in filas[1:]]
    return Tabla(tabla.pagina, tabla.indice, filas)


def unir_continuaciones(tablas: list[Tabla]) -> list[Tabla]:
    """Si una tabla de la página siguiente repite el encabezado (o tiene igual
    n.º de columnas sin encabezado de texto), se considera continuación."""
    salida: list[Tabla] = []
    for t in tablas:
        previa = salida[-1] if salida else None
        # Sólo entre páginas distintas (dos tablas en la misma página son tablas distintas)
        # y con la misma cantidad de columnas.
        if previa and t.filas and t.pagina > previa.pagina and len(t.encabezado) == len(previa.encabezado):
            if t.encabezado == previa.encabezado:
                # Encabezado repetido: se agregan las filas sin duplicarlo.
                previa.filas.extend(t.filas[1:])
                continue
            # Sin encabezado (la primera fila es de datos numéricos/vacíos): se agrega entera.
            if all(isinstance(c, float) or c == "" for c in t.filas[0]):
                previa.filas.extend(t.filas)
                continue
        # Copia de las filas: extender `previa` no debe modificar las tablas de entrada.
        salida.append(Tabla(t.pagina, t.indice, [list(f) for f in t.filas]))
    return salida
