# 32 · RAG sobre documentos propios

## Qué demuestra
**Retrieval-Augmented Generation** de punta a punta, sin servicios externos para
la parte de búsqueda: carga de documentos (.txt/.md, .pdf opcional),
fragmentación con solapamiento, **embeddings TF-IDF locales** en Python puro,
búsqueda por **similitud coseno**, prompt con fuentes numeradas y
**validación de citas** (se eliminan las citas inventadas por el LLM).

## Arquitectura
```
rag/documentos.py  -> carga y fragmentación (párrafos -> oraciones -> corte duro)
rag/embeddings.py  -> Embedder (Protocol), EmbedderTFIDF, IndiceVectorial (+ JSON)
rag/pipeline.py    -> recuperar -> prompt -> LLM -> validar citas
rag/llm.py         -> interfaz de LLM (OpenAI / Anthropic / falso)
rag/__main__.py    -> CLI indexar / preguntar
```
Si no hay fragmentos relevantes, **no se llama al LLM**: se responde que no hay información.

## Instalación
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # agregar ,pdf para soporte de PDF
```

## Uso
```bash
python -m rag indexar tests/docs indice.json
python -m rag preguntar indice.json "¿Cuántos días de vacaciones tengo?"   # LLM falso
OPENAI_API_KEY=... LLM_PROVEEDOR=openai python -m rag preguntar indice.json "..."
```

## Tests
```bash
pytest   # sin red: LLM falso y fixtures locales en tests/docs
```

## Limitaciones
- TF-IDF es léxico (no capta sinónimos); la interfaz `Embedder` permite cambiarlo por embeddings densos.
- Búsqueda exacta O(n): suficiente para miles de fragmentos; para millones, un índice ANN (FAISS, etc.).
