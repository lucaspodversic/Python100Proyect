# 33 · Notas automáticas de reuniones

## Qué demuestra
Pipeline **audio → transcripción → notas**: interfaz `Transcriptor` (Whisper por
API, Whisper local o falso), análisis con **LLM pidiendo JSON estricto** y
**heurísticas de respaldo** (regex de tareas, decisiones y fechas), porcentaje
de participación por persona y exportación a **Markdown**.

## Arquitectura
```
notas/transcripcion.py -> Segmento, Transcriptor (Protocol), WhisperAPI / WhisperLocal / Falso
notas/analisis.py      -> analizar() (LLM -> JSON, o heurísticas), participacion(), a_markdown()
notas/llm.py           -> interfaz de LLM (OpenAI / Anthropic / falso)
notas/__main__.py      -> CLI
```

## Instalación
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"        # ",local" agrega Whisper local
```

## Uso
```bash
python -m notas tests/reunion.json                    # sin audio ni red: segmentos de ejemplo
OPENAI_API_KEY=... LLM_PROVEEDOR=openai python -m notas reunion.mp3 notas.md
```

## Tests
```bash
pytest   # transcriptor falso + MockTransport: sin red ni claves
```

## Limitaciones
- La diarización es simple: depende de que el texto venga como "Nombre: ...". Para diarización real, pyannote.
- La API de Whisper tiene límite de 25 MB por archivo; audios largos habría que trocearlos.
