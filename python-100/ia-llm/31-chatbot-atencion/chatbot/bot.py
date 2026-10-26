"""Lógica del chatbot: intenciones, contexto, memoria y escalamiento a humano.

Flujo de cada mensaje:
1. Reglas rápidas (sin LLM): saludo, pedido de humano, despedida.
2. Recuperar FAQ relevantes.
3. Si no hay ninguna relevante -> respuesta honesta + ofrecer humano
   (evita que el LLM "alucine" políticas de la empresa).
4. Si hay, armar prompt con las FAQ como contexto + historial reciente.
5. Si el LLM falla, responder con la mejor FAQ directamente (degradación elegante).
"""
from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field

from chatbot.faq import BaseFAQ, normalizar
from chatbot.llm import ErrorLLM, Mensaje, ProveedorLLM

PROMPT_SISTEMA = """Sos el asistente de atención al cliente de {empresa}.
Respondé en español, breve y amable, usando SOLO la información de las FAQ provistas.
Si la información no alcanza, decí que no lo sabés y ofrecé derivar a una persona.
Nunca inventes precios, plazos ni políticas."""

# Reglas baratas que se resuelven sin LLM (rápido, gratis y predecible).
# \b = límite de palabra: "persona" matchea, "personalizado" no.
SALUDOS = {"hola", "buenas", "buen", "buenos", "hey"}
PEDIDO_HUMANO = re.compile(r"\b(humano|persona|operador|agente|asesor)\b", re.I)
DESPEDIDA = re.compile(r"\b(chau|adios|adiós|gracias|hasta luego)\b", re.I)


@dataclass
class Respuesta:
    texto: str
    fuente: str              # "regla" | "llm" | "faq" | "sin_info"
    escalar: bool = False    # True si hay que derivar a un humano
    faqs: list[str] = field(default_factory=list)


class Chatbot:
    def __init__(self, faq: BaseFAQ, llm: ProveedorLLM, empresa: str = "la empresa",
                 memoria_turnos: int = 6, max_fallos: int = 2) -> None:
        self.faq, self.llm, self.empresa = faq, llm, empresa
        # Memoria acotada: solo los últimos N mensajes (controla tokens/costo)
        self.historial: deque[Mensaje] = deque(maxlen=memoria_turnos * 2)
        # Tras `max_fallos` preguntas seguidas sin respuesta se deriva a un humano.
        self.max_fallos = max_fallos
        self._sin_respuesta_seguidas = 0
        # Mensajes que generaron escalamiento (en producción irían a un sistema
        # de tickets).
        self.tickets: list[str] = []

    def responder(self, texto: str) -> Respuesta:
        texto = texto.strip()[:2000]  # límite para evitar prompts gigantes
        r = self._procesar(texto)
        self.historial.append(Mensaje("user", texto))
        self.historial.append(Mensaje("assistant", r.texto))
        if r.escalar:
            self.tickets.append(texto)
        return r

    def _procesar(self, texto: str) -> Respuesta:
        tokens = normalizar(texto)
        palabras = set(re.findall(r"\w+", texto.lower()))
        # Pedir una persona tiene prioridad sobre todo: nunca se lo hace esperar.
        if PEDIDO_HUMANO.search(texto):
            return Respuesta("Te derivo con una persona del equipo. ¡Gracias por la paciencia!", "regla", escalar=True)
        # Solo si el mensaje es corto: "gracias, ¿y los envíos?" sigue siendo pregunta.
        if DESPEDIDA.search(texto) and len(tokens) <= 3:
            return Respuesta("¡Gracias por escribirnos! Que tengas un buen día.", "regla")
        # Ídem: "hola, ¿cuánto tarda el envío?" no se responde con un saludo.
        if palabras & SALUDOS and len(tokens) <= 2:
            return Respuesta(f"¡Hola! Soy el asistente de {self.empresa}. ¿En qué te puedo ayudar?", "regla")

        encontradas = self.faq.buscar(texto)
        if not encontradas:
            self._sin_respuesta_seguidas += 1
            escalar = self._sin_respuesta_seguidas >= self.max_fallos
            extra = " Te derivo con una persona." if escalar else " ¿Podés reformularlo o querés hablar con una persona?"
            return Respuesta("No encontré información sobre eso." + extra, "sin_info", escalar=escalar)
        # Una pregunta respondida reinicia el contador de fallos.
        self._sin_respuesta_seguidas = 0

        # Prompt: instrucciones + FAQ como contexto + historial + mensaje actual.
        # El historial va antes del mensaje nuevo para mantener el orden real.
        contexto = "\n\n".join(f"P: {e.pregunta}\nR: {e.respuesta}" for e, _ in encontradas)
        mensajes = [Mensaje("system", PROMPT_SISTEMA.format(empresa=self.empresa)),
                    Mensaje("system", f"FAQ relevantes:\n{contexto}"),
                    *self.historial, Mensaje("user", texto)]
        preguntas = [e.pregunta for e, _ in encontradas]
        try:
            # Temperatura baja: en atención al cliente se busca precisión, no creatividad.
            salida = self.llm.completar(mensajes, temperatura=0.2).strip()
            if salida:
                return Respuesta(salida, "llm", faqs=preguntas)
        except ErrorLLM:
            pass  # caemos a la respuesta literal de la FAQ
        return Respuesta(encontradas[0][0].respuesta, "faq", faqs=preguntas)
