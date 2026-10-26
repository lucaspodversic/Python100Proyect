"""Tests del clasificador y métricas (LLM falso, sin red)."""
import csv
from pathlib import Path

import pytest

from tickets.clasificador import CATEGORIAS, clasificar, construir_prompt, por_claves
from tickets.llm import ProveedorFalso
from tickets.metricas import matriz_confusion, reporte, tabla_matriz

DATOS = list(csv.DictReader(open(Path(__file__).parent / "etiquetados.csv", encoding="utf-8")))
ETIQ = list(CATEGORIAS)


@pytest.mark.parametrize("texto,cat,equipo", [
    # "cobraron" (3) => facturación. "iniciar sesion" (3) => cuenta.
    # "paquete" (3) + "llego" (2) => envíos. Sin claves => otro.
    ("Me cobraron dos veces", "facturacion", "Finanzas"),
    ("No puedo iniciar sesión", "cuenta", "Soporte N1"),
    ("El paquete no llegó", "envios", "Logística"),
    ("Hola, una consulta general", "otro", "Soporte N1"),
])
def test_por_claves(texto, cat, equipo):
    c = por_claves(texto)
    assert (c.categoria, c.equipo, c.origen) == (cat, equipo, "claves")


def test_prioridad_por_urgencia():
    # Urgencia: producción 3 + todos los clientes 3 + urgente 2 = 8 =>
    # 1 + 8 // 2 = 5 => tope 3 => crítica.
    assert por_claves("Error en producción, afecta a todos los clientes, urgente").prioridad == "critica"
    # "app" suma 1 (y "lenta" no empieza con "lento") y no hay urgencia => media.
    assert por_claves("La app está lenta").prioridad == "media"
    # Nada reconocido => baja.
    assert por_claves("consulta").prioridad == "baja"


def test_llm_valido():
    # Texto antes del JSON y mayúsculas: igual se acepta (se pasa a minúsculas).
    llm = ProveedorFalso(respuestas=['Claro: {"categoria": "TECNICO", "prioridad": "alta", "confianza": 0.95}'])
    c = clasificar("algo raro pasa", llm)
    assert (c.categoria, c.prioridad, c.origen, c.equipo) == ("tecnico", "alta", "llm", "Soporte N2")


@pytest.mark.parametrize("salida", [
    '{"categoria": "marketing", "prioridad": "alta", "confianza": 0.9}',   # fuera del conjunto
    '{"categoria": "tecnico", "prioridad": "urgentísima", "confianza": 0.9}',
    '{"categoria": "tecnico", "prioridad": "alta", "confianza": 0.2}',     # poca confianza
    # Sin objeto JSON => AttributeError capturado => palabras clave.
    "no es json",
])
def test_llm_invalido_cae_a_claves(salida):
    assert clasificar("Me cobraron dos veces", ProveedorFalso(respuestas=[salida])).origen == "claves"


def test_prompt_incluye_etiquetas_y_ejemplos():
    sistema = construir_prompt("x")[0].contenido
    assert "facturacion, tecnico, cuenta, envios, otro" in sistema and "cobraron dos veces" in sistema


def test_metricas_conocidas():
    reales = ["a", "a", "b", "b"]
    pred = ["a", "b", "b", "b"]
    # 3 de 4 aciertos => 0,75. Fila a: 1 bien, 1 predicha como b => [1, 1];
    # fila b: 2 bien => [0, 2]. Clase a: precisión 1/1 = 1,0, recall 1/2 = 0,5,
    # F1 = 2 x 1 x 0,5 / 1,5 = 0,667.
    r = reporte(reales, pred, ["a", "b"])
    assert r["exactitud"] == 0.75 and r["matriz"] == [[1, 1], [0, 2]]
    assert r["por_clase"]["a"] == {"precision": 1.0, "recall": 0.5, "f1": 0.667, "soporte": 2}
    assert "real\\pred" in tabla_matriz(r["matriz"], ["a", "b"])
    with pytest.raises(ValueError):
        # Largos distintos => ValueError por zip(strict=True).
        matriz_confusion(["a"], [], ["a"])


def test_evaluacion_dataset_por_claves():
    pred = [clasificar(f["texto"]).categoria for f in DATOS]
    r = reporte([f["categoria"] for f in DATOS], pred, ETIQ)
    # Umbral de regresión: si se tocan las claves y baja la exactitud, falla.
    assert r["exactitud"] >= 0.8   # línea base del clasificador sin LLM
    assert sum(map(sum, r["matriz"])) == len(DATOS)
