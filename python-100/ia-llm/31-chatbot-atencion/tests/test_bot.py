"""Tests del chatbot con proveedor falso (sin red)."""
from pathlib import Path

import pytest

from chatbot.bot import Chatbot
from chatbot.faq import BaseFAQ, normalizar
from chatbot.llm import ErrorLLM, ProveedorFalso

FAQ = BaseFAQ.desde_json(Path(__file__).parent.parent / "datos" / "faq.json")


# mensajes[0] = sistema, mensajes[1] = FAQ relevantes. Toma la primera "R: ".
def eco_contexto(mensajes):
    """LLM falso: responde citando la primera FAQ del contexto."""
    contexto = mensajes[1].contenido
    return "Según nuestras FAQ: " + contexto.split("R: ")[1].split("\n")[0]


def test_normalizar():
    # Sin tildes ni signos, "los" es palabra vacía y "envios" pierde la s.
    assert normalizar("¿Cuánto tardan los ENVÍOS?") == ["cuanto", "tardan", "envio"]


def test_busqueda_faq():
    top = FAQ.buscar("cuanto tarda el envio de mi pedido")
    assert top[0][0].categoria == "envios"
    # Ninguna palabra en común con las FAQ => lista vacía.
    assert FAQ.buscar("receta de empanadas") == []


def test_reglas_sin_llm():
    llm = ProveedorFalso()
    bot = Chatbot(FAQ, llm)
    assert bot.responder("Hola").fuente == "regla"
    r = bot.responder("quiero hablar con una persona")
    assert r.escalar and bot.tickets == ["quiero hablar con una persona"]
    # Las reglas no gastan llamadas al LLM.
    assert llm.llamadas == []


def test_respuesta_con_contexto_y_historial():
    llm = ProveedorFalso(funcion=eco_contexto)
    bot = Chatbot(FAQ, llm, empresa="ACME")
    r = bot.responder("¿Qué medios de pago aceptan?")
    assert r.fuente == "llm" and "tarjeta" in r.texto
    assert "ACME" in llm.llamadas[0][0].contenido
    bot.responder("¿y cómo hago una devolución?")
    # El segundo prompt incluye el turno anterior en el historial
    assert any(m.rol == "assistant" and "tarjeta" in m.contenido for m in llm.llamadas[1])


# Primer fallo: ofrece reformular. Segundo seguido: escala (max_fallos=2).
def test_sin_info_escala_tras_fallos():
    bot = Chatbot(FAQ, ProveedorFalso(), max_fallos=2)
    assert not bot.responder("¿venden autos?").escalar
    assert bot.responder("¿y motos?").escalar


def test_fallback_si_llm_falla():
    def rompe(_):
        raise ErrorLLM("sin conexión")
    r = Chatbot(FAQ, ProveedorFalso(funcion=rompe)).responder("horarios de atención")
    assert r.fuente == "faq" and "lunes a viernes" in r.texto


# 5 turnos = 10 mensajes, pero la memoria guarda 2 turnos * 2 = 4.
def test_memoria_acotada():
    bot = Chatbot(FAQ, ProveedorFalso(), memoria_turnos=2)
    for _ in range(5):
        bot.responder("medios de pago")
    assert len(bot.historial) == 4
