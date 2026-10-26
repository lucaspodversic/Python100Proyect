"""Algoritmos de ordenamiento escritos como **generadores de pasos**.

Cada algoritmo recibe una lista y la ordena *in situ*, pero en lugar de
hacerlo de corrido "cede" (``yield``) un :class:`Paso` cada vez que compara,
intercambia o escribe. Así la GUI puede animar el proceso a su ritmo, y los
tests pueden verificar que reproducir los pasos sobre una copia del arreglo
original da exactamente el mismo resultado.

Tipos de paso:

* ``comparar(i, j)``: solo lectura; no cambia el arreglo.
* ``intercambiar(i, j)``: ``a[i], a[j] = a[j], a[i]``.
* ``escribir(i, valor)``: ``a[i] = valor`` (merge sort necesita un buffer auxiliar).
* ``ordenado(i)``: marca la posición ``i`` como definitiva (solo visual).
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Literal

TipoPaso = Literal["comparar", "intercambiar", "escribir", "ordenado"]


@dataclass(frozen=True)
class Paso:
    """Un evento elemental del algoritmo: 'comparar' (i, j), 'intercambiar' (i, j), 'escribir'
    (pone ``valor`` en i, lo usa merge sort, que no intercambia) u 'ordenado' (la
    posición i ya tiene su valor final). La GUI solo necesita estos eventos para animar
    y contar.
    """
    tipo: TipoPaso
    i: int
    j: int = -1          # segundo índice (comparar/intercambiar)
    valor: int = 0       # para "escribir"


Generador = Iterator[Paso]


def _swap(a: list[int], i: int, j: int) -> Paso:
    """Intercambia a[i] y a[j] en la lista de trabajo y devuelve el Paso que lo describe, así
    el intercambio y su evento no pueden desincronizarse.
    """
    a[i], a[j] = a[j], a[i]
    return Paso("intercambiar", i, j)


def burbuja(a: list[int]) -> Generador:
    """O(n²). Con corte temprano si una pasada no intercambia nada."""
    n = len(a)
    for fin in range(n - 1, 0, -1):
        hubo = False
        for i in range(fin):
            yield Paso("comparar", i, i + 1)
            if a[i] > a[i + 1]:
                yield _swap(a, i, i + 1)
                hubo = True
        yield Paso("ordenado", fin)
        if not hubo:
            break
    for k in range(n):
        yield Paso("ordenado", k)


def seleccion(a: list[int]) -> Generador:
    """Selección: en cada vuelta busca el mínimo del tramo no ordenado (n-1-i comparaciones,
    siempre, sin importar el orden de entrada: n(n-1)/2 en total) y lo pone en i con a
    lo sumo un intercambio. Pocas escrituras, muchas comparaciones.
    """
    n = len(a)
    for i in range(n):
        m = i
        for j in range(i + 1, n):
            yield Paso("comparar", m, j)
            if a[j] < a[m]:
                m = j
        if m != i:
            yield _swap(a, i, m)
        yield Paso("ordenado", i)


def insercion(a: list[int]) -> Generador:
    """Inserción: lleva a[i] hacia la izquierda con intercambios adyacentes hasta que el
    anterior sea <=. Con datos ya ordenados hace solo n-1 comparaciones (mejor caso
    lineal); el '<=' lo hace estable. Las posiciones se marcan como ordenadas recién al
    final, porque un elemento posterior todavía puede desplazar a los anteriores.
    """
    for i in range(1, len(a)):
        j = i
        while j > 0:
            yield Paso("comparar", j - 1, j)
            if a[j - 1] <= a[j]:
                break
            yield _swap(a, j - 1, j)
            j -= 1
    for k in range(len(a)):
        yield Paso("ordenado", k)


def shell(a: list[int]) -> Generador:
    """Inserción con saltos decrecientes (secuencia de Ciura, extendida ×2.25)."""
    n = len(a)
    gaps = [1, 4, 10, 23, 57, 132, 301, 701]
    while gaps[-1] < n:
        gaps.append(int(gaps[-1] * 2.25))
    for g in reversed([g for g in gaps if g < n] or [1]):
        for i in range(g, n):
            j = i
            while j >= g:
                yield Paso("comparar", j - g, j)
                if a[j - g] <= a[j]:
                    break
                yield _swap(a, j - g, j)
                j -= g
    for k in range(n):
        yield Paso("ordenado", k)


def merge(a: list[int]) -> Generador:
    """Merge sort ascendente (bottom-up): sin recursión, usa buffer y pasos ``escribir``."""
    n = len(a)
    ancho = 1
    while ancho < n:
        for ini in range(0, n, 2 * ancho):
            medio, fin = min(ini + ancho, n), min(ini + 2 * ancho, n)
            izq, der = a[ini:medio], a[medio:fin]
            i = j = 0
            k = ini
            while i < len(izq) and j < len(der):
                yield Paso("comparar", ini + i, medio + j)
                if izq[i] <= der[j]:       # <= mantiene la estabilidad
                    v = izq[i]; i += 1
                else:
                    v = der[j]; j += 1
                a[k] = v
                yield Paso("escribir", k, valor=v)
                k += 1
            for v in izq[i:] + der[j:]:
                a[k] = v
                yield Paso("escribir", k, valor=v)
                k += 1
        ancho *= 2
    for k in range(n):
        yield Paso("ordenado", k)


def quick(a: list[int]) -> Generador:
    """Quicksort con partición de Lomuto, pivote = mediana de tres, y pila explícita
    (evita recursión profunda) procesando primero la partición más chica."""
    pila = [(0, len(a) - 1)]
    while pila:
        lo, hi = pila.pop()
        if lo >= hi:
            if lo == hi:
                yield Paso("ordenado", lo)
            continue
        mid = (lo + hi) // 2
        # Mediana de tres: deja la mediana en a[hi].
        for x, y in ((lo, mid), (lo, hi), (mid, hi)):
            yield Paso("comparar", x, y)
            if a[x] > a[y]:
                yield _swap(a, x, y)
        yield _swap(a, mid, hi)
        piv = a[hi]
        i = lo
        for j in range(lo, hi):
            yield Paso("comparar", j, hi)
            if a[j] < piv:
                if i != j:
                    yield _swap(a, i, j)
                i += 1
        if i != hi:
            yield _swap(a, i, hi)
        yield Paso("ordenado", i)
        partes = sorted([(lo, i - 1), (i + 1, hi)], key=lambda p: p[1] - p[0], reverse=True)
        pila.extend(partes)  # la más chica queda arriba de la pila


def heap(a: list[int]) -> Generador:
    """Heapsort: primero arma un max-heap en el arreglo (hundiendo desde la mitad hacia la
    raíz) y después intercambia la raíz (el máximo) con el final del heap, que queda
    ordenado, y vuelve a hundir. O(n log n) siempre y sin memoria extra, pero no es
    estable.
    """
    n = len(a)

    def hundir(raiz: int, fin: int) -> Generador:
        """Baja ``raiz`` mientras algún hijo sea mayor, considerando solo índices < fin. Los
        hijos de k están en 2k+1 y 2k+2. Primero compara los dos hijos y después el
        mayor con la raíz.
        """
        while (hijo := 2 * raiz + 1) < fin:
            if hijo + 1 < fin:
                yield Paso("comparar", hijo, hijo + 1)
                if a[hijo + 1] > a[hijo]:
                    hijo += 1
            yield Paso("comparar", raiz, hijo)
            if a[raiz] >= a[hijo]:
                return
            yield _swap(a, raiz, hijo)
            raiz = hijo

    for r in range(n // 2 - 1, -1, -1):
        yield from hundir(r, n)
    for fin in range(n - 1, 0, -1):
        yield _swap(a, 0, fin)
        yield Paso("ordenado", fin)
        yield from hundir(0, fin)
    if n:
        yield Paso("ordenado", 0)


ALGORITMOS: dict[str, Callable[[list[int]], Generador]] = {
    "Burbuja": burbuja, "Selección": seleccion, "Inserción": insercion, "Shell": shell,
    "Merge sort": merge, "Quicksort": quick, "Heapsort": heap,
}

COMPLEJIDAD = {
    "Burbuja": "O(n²)", "Selección": "O(n²)", "Inserción": "O(n²) · O(n) casi ordenado",
    "Shell": "≈O(n^1.3)", "Merge sort": "O(n log n) estable", "Quicksort": "O(n log n) prom.",
    "Heapsort": "O(n log n) in situ",
}


def aplicar(a: list[int], paso: Paso) -> None:
    """Aplica un paso a otra copia del arreglo (lo usa la GUI y los tests)."""
    if paso.tipo == "intercambiar":
        a[paso.i], a[paso.j] = a[paso.j], a[paso.i]
    elif paso.tipo == "escribir":
        a[paso.i] = paso.valor
