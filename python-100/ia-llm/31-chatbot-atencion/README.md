# 31 · Chatbot de atención al cliente

## Qué demuestra
Un chatbot que combina **reglas** (saludo, pedido de humano), **recuperación de
FAQ** (mini-RAG léxico con IDF) y un **LLM intercambiable** (OpenAI, Anthropic
o un proveedor falso determinista). Incluye memoria acotada, escalamiento a
humano y degradación elegante si el LLM falla.

## Arquitectura
```
chatbot/llm.py   -> Protocol ProveedorLLM + adaptadores OpenAI/Anthropic (httpx) + ProveedorFalso
chatbot/faq.py   -> normalización de texto, índice IDF, búsqueda de FAQ
chatbot/bot.py   -> orquestación: reglas -> FAQ -> LLM -> fallback
chatbot/__main__ -> chat por consola
datos/faq.json   -> base de conocimiento de ejemplo
```
El LLM solo recibe las FAQ relevantes y la instrucción de no inventar: si no
hay FAQ que aplique, el bot **no llama al LLM** y ofrece derivar a una persona.

## Instalación
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Uso
```bash
python -m chatbot                       # proveedor falso (sin red)
export OPENAI_API_KEY=...               # la clave SOLO por variable de entorno
LLM_PROVEEDOR=openai python -m chatbot
LLM_PROVEEDOR=anthropic ANTHROPIC_API_KEY=... python -m chatbot
```

## Tests
```bash
pytest     # sin red ni claves: proveedor falso y httpx.MockTransport
```

## Limitaciones
- La búsqueda es léxica: no entiende sinónimos ("demora" ≠ "tarda"). Para eso, embeddings (ver proyecto 32).
- Los "tickets" de escalamiento quedan en memoria; en producción irían a un helpdesk.
