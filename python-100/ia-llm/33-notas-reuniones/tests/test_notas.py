"""Tests de transcripción (falsa / API simulada) y análisis. Sin red."""
import json
from pathlib import Path

import httpx

from notas.analisis import a_markdown, analizar, heuristicas, participacion
from notas.llm import ProveedorFalso
from notas.transcripcion import TranscriptorFalso, TranscriptorWhisperAPI, separar_hablante

FIX = Path(__file__).parent / "reunion.json"
# Reunión de 90 s: Ana 0-20 y 50-70 (40 s), Beto 20-50 (30 s), Caro 70-90 (20 s).
SEGS = TranscriptorFalso(fixture=FIX).transcribir("ignorado.mp3")


def test_participacion():
    # 40/90 = 44,4 %, 30/90 = 33,3 %, 20/90 = 22,2 %, ordenado de mayor a menor.
    assert participacion(SEGS) == {"Ana": 44.4, "Beto": 33.3, "Caro": 22.2}


def test_heuristicas():
    # Tareas: "Voy a terminar los tests el viernes" (Beto), "Caro, podés
    # preparar..." (de Caro aunque lo dijo Ana) y "Hay que revisar el
    # presupuesto" (Caro lo dijo, sin fecha).
    decisiones, tareas = heuristicas(SEGS)
    assert decisiones == ["Decidimos lanzar el 15/11."]
    assert [(t.responsable, t.fecha) for t in tareas] == [
        ("Beto", "el viernes"),
        ("Caro", "la semana que viene"),   # "Caro, podés..." lo dijo Ana, pero la tarea es de Caro
        ("Caro", None),
    ]


def test_analisis_con_llm_json():
    # Respuesta envuelta en ```json ... ```, como suelen devolver los LLM.
    salida = '```json\n{"resumen": "Se planificó el lanzamiento.", "decisiones": ["Lanzar el 15/11"], ' \
             '"tareas": [{"responsable": "Beto", "tarea": "Tests", "fecha": "viernes"}]}\n```'
    llm = ProveedorFalso(respuestas=[salida])
    n = analizar(SEGS, llm)
    assert n.origen == "llm" and n.tareas[0].responsable == "Beto"
    # El prompt incluye la transcripción con el formato "hablante: texto".
    assert "Beto: El backend" in llm.llamadas[0][1].contenido


def test_analisis_fallback_si_json_invalido():
    n = analizar(SEGS, ProveedorFalso(respuestas=["no sé hacer JSON"]))
    # Duración = fin del último segmento (90 s).
    assert n.origen == "heuristica" and len(n.tareas) == 3 and n.duracion == 90


def test_markdown():
    md = a_markdown(analizar(SEGS, ProveedorFalso(respuestas=["x"])), "Sprint")
    assert md.startswith("# Sprint") and "| Beto |" in md and "- Ana: 44.4%" in md


def test_separar_hablante():
    assert separar_hablante("Ana: hola") == ("Ana", "hola")
    assert separar_hablante("hola a todos") == ("?", "hola a todos")


# La API de Whisper simulada con MockTransport: se verifica el modelo y la
# clave enviados y que "Ana: ..." se separe en hablante y texto.
def test_whisper_api_simulada(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    audio = tmp_path / "a.mp3"; audio.write_bytes(b"\x00\x01")

    def manejador(req: httpx.Request):
        assert b"whisper-1" in req.content and req.headers["authorization"] == "Bearer k"
        return httpx.Response(200, json={"segments": [{"start": 0, "end": 3, "text": "Ana: Voy a revisar."}]})

    segs = TranscriptorWhisperAPI(cliente=httpx.Client(transport=httpx.MockTransport(manejador))).transcribir(audio)
    assert segs[0].hablante == "Ana" and segs[0].texto == "Voy a revisar."
