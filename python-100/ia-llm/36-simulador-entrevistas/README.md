# 36 · Simulador de entrevistas laborales

## Qué demuestra
Un entrevistador virtual con **banco de preguntas** filtrable (rol/nivel,
selección reproducible que cubre competencias distintas), una **máquina de
estados** (inicio → preguntando → repregunta → finalizada), **evaluación con
LLM** en JSON validado (rango 1-10) y **respaldo determinista** por palabras
clave, más un informe final por competencia.

## Arquitectura
```
entrevistas/banco.py      -> Pregunta, cargar_banco(), seleccionar()
entrevistas/evaluador.py  -> evaluar() (LLM) y evaluar_por_claves() (respaldo)
entrevistas/sesion.py     -> Sesion (estados, repreguntas, tiempos, informe)
entrevistas/datos/        -> preguntas.json (editable)
entrevistas/llm.py        -> interfaz de LLM (OpenAI / Anthropic / falso)
```

## Instalación
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Uso
```bash
python -m entrevistas backend junior 3                 # LLM falso -> evaluación por claves
OPENAI_API_KEY=... LLM_PROVEEDOR=openai python -m entrevistas backend senior 4
```

## Tests
```bash
pytest   # LLM falso y reloj inyectado: sin red, deterministas
```

## Limitaciones
- La evaluación por claves es superficial (busca menciones, no comprensión); es solo un respaldo.
- La entrevista es por texto; podría sumarse voz con la interfaz de transcripción del proyecto 33.
