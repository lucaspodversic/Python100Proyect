# 34 · Asistente de email

## Qué demuestra
Un asistente que **lee .eml** con la biblioteca estándar (`email`, encabezados
codificados, multipart, adjuntos, HTML→texto, quita historial citado),
**prioriza** con heurísticas explicables, **resume** y **redacta borradores**
con un LLM intercambiable, y arma la respuesta con los encabezados de hilo
correctos (`In-Reply-To`, `References`).

## Arquitectura
```
correo/parser.py     -> leer_eml() -> Correo, html_a_texto(), quitar_citas()
correo/asistente.py  -> priorizar(), resumir(), redactar_respuesta(), construir_borrador()
correo/llm.py        -> interfaz de LLM (OpenAI / Anthropic / falso)
correo/__main__.py   -> CLI
```
**Seguridad:** el correo se envía al LLM delimitado como *datos* con una guarda
contra *prompt injection*, y el asistente **nunca envía** correos: solo guarda
un borrador `.eml` para revisión humana.

## Instalación
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Uso
```bash
python -m correo tests/pedido.eml "enviar la cotización y confirmar soporte" formal
OPENAI_API_KEY=... LLM_PROVEEDOR=openai python -m correo mensaje.eml "rechazar amablemente"
```

## Tests
```bash
pytest   # LLM falso, fixture .eml local, sin red
```

## Limitaciones
- No se conecta a IMAP/Gmail: trabaja con archivos .eml (exportables desde cualquier cliente).
- La guarda anti-inyección reduce el riesgo pero no lo elimina; por eso el diseño exige revisión humana.
