# 93 · Motor de búsqueda simple

Indexa una carpeta de documentos (`.txt`, `.md`, `.rst`) y busca por palabras clave. Los resultados se ordenan por **relevancia BM25** y muestran un fragmento con las coincidencias resaltadas.

## Qué demuestra

- **Índice invertido con posiciones**: `postings[término][doc] = [posiciones]`.
- **Análisis de texto en español**:
  - Plegado de tildes (la ñ se conserva) y stopwords.
  - Stemmer ligero por sufijos: `programación`, `programaciones` y `programar` dan `program`.
- **Ranking BM25** (k1=1,5; b=0,75):
  - La frecuencia de un término satura, así que repetir una palabra no infla la puntuación.
  - La longitud del documento se normaliza.
  - Hay bonus por coincidencias en el **título** y por **frase exacta**.
- **Sintaxis de consulta**:
  - `palabra` es opcional y suma.
  - `+palabra` es obligatoria.
  - `-palabra` excluye.
  - `"frase exacta"` exige adyacencia y orden. Las stopwords cuentan como posición: `"base de datos"` no coincide con `base … datos`.
- **Fragmentos**: una ventana deslizante de 20 palabras con más coincidencias, con `[resaltado]`.
- **Indexación incremental** por `mtime`: detecta documentos nuevos, modificados y eliminados.
- **Persistencia** en JSON versionado.
- Sin dependencias externas: solo la biblioteca estándar.

## Arquitectura

```
buscador/
├── texto.py     # plegar, raiz (stemmer), tokens_con_posicion, STOPWORDS
├── consulta.py  # Consulta + parsear (opcionales, +obligatorios, -excluidos, "frases")
├── indice.py    # Indice (agregar/quitar/indexar_carpeta, BM25, frases, guardar/cargar), fragmento
└── cli.py       # indexar | buscar
```

## Instalación y uso

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m buscador --indice indice.json indexar tests/corpus
python -m buscador --indice indice.json buscar 'python "base de datos" -mongodb'
```

## Tests

```bash
pytest
```

- Usan un corpus pequeño en `tests/corpus/`.
- Cubren normalización, stemming, parser de consultas, orden por relevancia, frases (incluido el orden), exclusiones, obligatorios, el peso del título, los fragmentos, la indexación incremental, la persistencia y la CLI.

## Limitaciones

- El stemmer es heurístico: no maneja verbos irregulares ni distingue homógrafos. Para más calidad, usá Snowball (`snowballstemmer`).
- El índice vive en memoria y se guarda como JSON con el texto completo; el tamaño razonable es de miles de documentos, no de millones (para eso, SQLite FTS5, Whoosh o Elasticsearch).
- No hay corrección ortográfica, sinónimos ni búsqueda difusa.
- Al cargar, el índice se reconstruye desde el texto: es simple y robusto, pero no es instantáneo con corpus grandes.
