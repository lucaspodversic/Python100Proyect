"""Tests del simulador de entrevistas (LLM falso, reloj falso)."""
import json

import pytest

from entrevistas.banco import cargar_banco, seleccionar
from entrevistas.evaluador import evaluar, evaluar_por_claves
from entrevistas.llm import ProveedorFalso
from entrevistas.sesion import Estado, Sesion

BANCO = cargar_banco()
PY1 = next(p for p in BANCO if p.id == "py1")


# Cada lectura avanza 30 s: entre mostrar la pregunta (1 lectura) y
# responder (otra) pasan exactamente 30 s.
class Reloj:
    def __init__(self): self.t = 0.0
    def __call__(self): self.t += 30; return self.t


def test_seleccion_reproducible_y_variada():
    a = seleccionar(BANCO, "backend", "junior", 3, semilla=1)
    assert a == seleccionar(BANCO, "backend", "junior", 3, semilla=1)
    # Primero se cubre una pregunta por competencia antes de repetir.
    assert len({p.competencia for p in a}) == 3          # python, bd y comunicación
    assert all(p.rol in ("backend", "*") for p in a)
    with pytest.raises(ValueError):
        seleccionar(BANCO, "chef", "junior", 2)


def test_evaluacion_por_claves():
    # Claves de py1: mutable, inmutable, hash, rendimiento. Se mencionan 3 de
    # 4 => round(7,5) = 8 (Python redondea al par). Falta "rendimiento".
    ev = evaluar_por_claves(PY1, "La lista es mutable y la tupla es inmutable, por eso la tupla se puede usar como clave (hash).")
    assert ev.puntaje == 8 and ev.origen == "claves" and "Podría mencionar: rendimiento" in ev.mejoras
    # 0 claves => max(1, 0) = 1; la penalización por corta no baja de 1.
    assert evaluar_por_claves(PY1, "No sé").puntaje == 1


def test_evaluacion_llm_valida_y_fallback():
    ok = ProveedorFalso(respuestas=['{"puntaje": 9, "fortalezas": ["clara"], "mejoras": [], "repregunta": null}'])
    assert evaluar(PY1, "respuesta", ok).puntaje == 9
    # 42 está fuera de 1..10 => se ignora el LLM y se evalúa por claves.
    fuera_rango = ProveedorFalso(respuestas=['{"puntaje": 42}'])
    assert evaluar(PY1, "la lista es mutable", fuera_rango).origen == "claves"
    assert evaluar(PY1, "   ", ok).origen == "regla"


def test_flujo_con_repregunta_e_informe():
    # Puntajes 6 (intermedio con repregunta), 8 (respuesta a la repregunta) y 5.
    respuestas = [
        json.dumps({"puntaje": 6, "fortalezas": [], "mejoras": ["profundizar"], "repregunta": "¿Y en rendimiento?"}),
        json.dumps({"puntaje": 8, "fortalezas": ["bien"], "mejoras": [], "repregunta": None}),
        json.dumps({"puntaje": 5, "fortalezas": [], "mejoras": ["ejemplos"], "repregunta": None}),
    ]
    preguntas = [PY1, next(p for p in BANCO if p.id == "db1")]
    s = Sesion(preguntas, ProveedorFalso(respuestas=respuestas), reloj=Reloj())
    assert s.iniciar() == PY1.texto
    _, sig = s.responder("La lista es mutable")
    assert s.estado is Estado.REPREGUNTA and sig == "¿Y en rendimiento?"
    _, sig = s.responder("Las tuplas son algo más livianas")
    assert sig == preguntas[1].texto
    _, sig = s.responder("Un índice acelera búsquedas")
    assert sig is None and s.estado is Estado.FINALIZADA
    # Promedio (6 + 8 + 5) / 3 = 6,33 => 6,3 => "a revisar". Python: (6 + 8)
    # / 2 = 7,0; bases de datos: 5,0. Tiempo: 3 turnos x 30 s = 90.
    inf = s.informe()
    assert inf["puntaje_global"] == 6.3 and inf["veredicto"] == "a revisar"
    assert inf["por_competencia"] == {"python": 7.0, "bases de datos": 5.0}
    assert inf["tiempo_total_s"] == 90 and s.turnos[1].es_repregunta


# Responder o pedir informe antes de iniciar, o iniciar dos veces => error.
def test_transiciones_invalidas():
    s = Sesion([PY1], ProveedorFalso())
    with pytest.raises(RuntimeError):
        s.responder("x")
    with pytest.raises(RuntimeError):
        s.informe()
    s.iniciar()
    with pytest.raises(RuntimeError):
        s.iniciar()
