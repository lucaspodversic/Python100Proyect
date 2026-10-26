"""Tests de los algoritmos y del reproductor. Los datos aleatorios usan semillas fijas, así que
los tests son deterministas.
"""
import random

import pytest

from ordenvis.algoritmos import ALGORITMOS, Paso, aplicar, burbuja, insercion, merge
from ordenvis.reproductor import Reproductor, arreglo_aleatorio

# Casos borde y típicos: vacío, un elemento, dos invertidos, todos iguales (estabilidad y '<='),
# ya ordenado (mejor caso), invertido (peor caso para burbuja/inserción), mixto con repetidos
# y 40 valores pseudoaleatorios con semillas fijas (reproducibles).
CASOS = [[], [1], [2, 1], [3, 3, 3], list(range(20)), list(range(20, 0, -1)),
         [5, 1, 4, 2, 8, 0, 2, 9, 7, 7], [random.Random(s).randint(0, 50) for s in range(40)]]


@pytest.mark.parametrize("nombre", list(ALGORITMOS))
@pytest.mark.parametrize("caso", CASOS, ids=range(len(CASOS)))
def test_ordena_y_los_pasos_reproducen_el_resultado(nombre, caso):
    """Para cada algoritmo × caso (vacío, uno, dos, repetidos, ordenado, invertido, mixto y 40
    aleatorios con semilla): el resultado está ordenado, los índices de cada paso son
    válidos y aplicar los pasos a una réplica da exactamente el mismo resultado. Esto
    último garantiza que la animación es fiel.
    """
    trabajo, replica = list(caso), list(caso)
    for paso in ALGORITMOS[nombre](trabajo):
        assert isinstance(paso, Paso)
        n = len(caso)
        assert 0 <= paso.i < n and (paso.j == -1 or 0 <= paso.j < n)
        aplicar(replica, paso)
    assert trabajo == sorted(caso)
    assert replica == trabajo  # los pasos describen fielmente lo que hizo el algoritmo


@pytest.mark.parametrize("nombre", list(ALGORITMOS))
def test_marca_todas_las_posiciones_como_ordenadas(nombre):
    """Cada algoritmo termina marcando las 30 posiciones como ordenadas, así la barra final
    queda toda verde.
    """
    datos = arreglo_aleatorio(30, semilla=1)
    marcadas = {p.i for p in ALGORITMOS[nombre](datos) if p.tipo == "ordenado"}
    assert marcadas == set(range(30))


def test_conteos_conocidos():
    """Burbuja sobre [3,2,1] necesita 3 intercambios (el número de inversiones). Inserción
    sobre datos ya ordenados hace n-1 = 9 comparaciones. Burbuja sobre datos ordenados
    no intercambia nada.
    """
    pasos = list(burbuja([3, 2, 1]))
    assert [p.tipo for p in pasos].count("intercambiar") == 3
    assert [p.tipo for p in insercion(list(range(10)))].count("comparar") == 9  # ya ordenado: n-1 comparaciones
    assert sum(p.tipo == "intercambiar" for p in burbuja(list(range(10)))) == 0


def test_merge_es_estable_y_usa_escrituras():
    """Merge de [2,1] escribe 1 en la posición 0 y 2 en la 1: trabaja con escrituras desde un
    auxiliar, no con intercambios.
    """
    pasos = list(merge([2, 1]))
    assert [(p.tipo, p.i, p.valor) for p in pasos if p.tipo == "escribir"] == [("escribir", 0, 1), ("escribir", 1, 2)]


def test_cuadraticos_vs_nlogn():
    """Con n = 200: burbuja hace del orden de n²/2 ≈ 20 000 comparaciones y merge sort del
    orden de n·log2 n ≈ 1 500; los umbrales /5 y /3 dejan mucho margen y no dependen de
    los datos exactos.
    """
    datos = arreglo_aleatorio(200, semilla=3)
    comps = {n: sum(p.tipo == "comparar" for p in ALGORITMOS[n](list(datos))) for n in ALGORITMOS}
    assert comps["Merge sort"] < comps["Burbuja"] / 5 and comps["Heapsort"] < comps["Selección"] / 3


def test_arreglo_aleatorio():
    """El modo aleatorio es una permutación de 1..n, reproducible con la misma semilla.
    'invertido' es n..1 y 'pocos' usa a lo sumo 4 valores distintos (muchos repetidos).
    n = 0 y un modo desconocido son errores.
    """
    assert sorted(arreglo_aleatorio(10, 1)) == list(range(1, 11))
    assert arreglo_aleatorio(10, 1) == arreglo_aleatorio(10, 1)
    assert arreglo_aleatorio(5, modo="invertido") == [5, 4, 3, 2, 1]
    assert len(set(arreglo_aleatorio(50, 2, "pocos"))) <= 4
    with pytest.raises(ValueError):
        arreglo_aleatorio(0)
    with pytest.raises(ValueError):
        arreglo_aleatorio(5, modo="x")


def test_reproductor():
    """El primer paso de burbuja sobre [3,1,2] compara 0 y 1 y queda resaltado. Al completar
    está ordenado y con todo marcado; el total de pasos es comparaciones + intercambios
    (burbuja no escribe). Reiniciar vuelve al arreglo original con contadores en 0. Un
    algoritmo desconocido es ValueError.
    """
    r = Reproductor([3, 1, 2], "Burbuja")
    hechos = r.avanzar(1)
    assert hechos[0].tipo == "comparar" and r.activos == (0, 1) and r.stats.comparaciones == 1
    r.completar()
    assert r.terminado and r.valores == [1, 2, 3] and r.ordenados == {0, 1, 2}
    assert r.stats.pasos == r.stats.comparaciones + r.stats.intercambios
    r.reiniciar()
    assert r.valores == [3, 1, 2] and not r.terminado and r.stats.pasos == 0
    with pytest.raises(ValueError):
        Reproductor([1], "Bogo")
