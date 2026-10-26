"""Tests del RAG: fragmentación, TF-IDF, búsqueda, citas. Sin red."""
import re
from pathlib import Path

import pytest

from rag.documentos import cargar_carpeta, fragmentar
from rag.embeddings import EmbedderTFIDF, IndiceVectorial, coseno
from rag.llm import ProveedorFalso
from rag.pipeline import RAG

DOCS = Path(__file__).parent / "docs"


@pytest.fixture(scope="module")
# scope="module": se indexa una sola vez para todos los tests (es de solo
# lectura). Fragmentos chicos (200) para que cada doc tenga varios.
def indice():
    ind = IndiceVectorial()
    ind.indexar(cargar_carpeta(DOCS, max_chars=200, solape=40))
    return ind


def test_fragmentar_respeta_tamano_y_solapa():
    texto = " ".join(f"Oración número {i} con algo de texto." for i in range(40))
    frs = fragmentar(texto, "x.txt", max_chars=150, solape=30)
    # ~40 oraciones de ~38 caracteres ≈ 1500 caracteres => más de 5 fragmentos
    # de 150. El tope es max_chars + solape (la cola se suma al inicio).
    assert len(frs) > 5 and all(len(f.texto) <= 150 + 30 for f in frs)
    assert frs[1].id == "x.txt#1"
    # el final de un fragmento reaparece al comienzo del siguiente
    assert frs[0].texto.split()[-1] in frs[1].texto.split()[:8]
    with pytest.raises(ValueError):
        fragmentar("x", "x", max_chars=10, solape=10)


def test_coseno_y_tfidf():
    assert coseno({"a": 1}, {"a": 2}) == pytest.approx(1)
    assert coseno({"a": 1}, {"b": 1}) == 0
    e = EmbedderTFIDF(); e.ajustar(["gato negro", "perro negro"])
    v = e.vectorizar("gato negro")
    # IDF: gato ln(3/2)+1 ≈ 1,41 contra negro ln(3/3)+1 = 1.
    assert v["gato"] > v["negro"]  # término más raro pesa más


def test_busqueda_recupera_documento_correcto(indice):
    top = indice.buscar("¿cuántos días de vacaciones tengo?")
    assert top[0][0].fuente == "vacaciones.md"
    assert indice.buscar("tope diario comidas")[0][0].fuente == "gastos.txt"
    # Ninguna palabra en el vocabulario => vector vacío => sin resultados.
    assert indice.buscar("astronomía cuántica") == []


# Simula un LLM que cita bien [1] y además inventa [9] (que no existe).
def responde_citando(mensajes):
    """LLM falso: toma la fuente [1] y cita, más una cita inventada [9]."""
    fuentes = mensajes[1].contenido
    primera = re.search(r"\[1\] \([^)]+\) ([^\n]+)", fuentes).group(1)
    return f"{primera[:60]} [1] [9]"


def test_rag_con_citas_y_limpieza(indice):
    llm = ProveedorFalso(funcion=responde_citando)
    r = RAG(indice, llm).preguntar("¿con cuánta anticipación pido vacaciones?")
    assert r.con_respaldo and r.citas[0]["fuente"] == "vacaciones.md"
    assert r.citas_invalidas == [9] and "[9]" not in r.texto
    assert "Fuentes:" in llm.llamadas[0][1].contenido


# Nada recuperado => respuesta fija y cero llamadas al LLM.
def test_rag_sin_contexto_no_llama_llm(indice):
    llm = ProveedorFalso()
    r = RAG(indice, llm).preguntar("receta de pizza napolitana")
    assert not r.con_respaldo and llm.llamadas == []


def test_rag_no_se(indice):
    r = RAG(indice, ProveedorFalso(respuestas=["NO_SE"])).preguntar("vacaciones en marte")
    assert not r.con_respaldo


# El índice guardado y recargado devuelve el mismo primer resultado.
def test_persistencia(indice, tmp_path):
    ruta = tmp_path / "indice.json"
    indice.guardar(ruta)
    otro = IndiceVectorial.cargar(ruta)
    assert otro.buscar("taxis")[0][0].id == indice.buscar("taxis")[0][0].id
