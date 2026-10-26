# 95 · Música procedural con reglas armónicas

Compositor que genera piezas cortas (melodía + acordes + bajo) a partir de una
semilla, respetando reglas de armonía tonal. Las exporta a **WAV** (síntesis
propia con numpy) y **MIDI**, y opcionalmente las reproduce con **pygame**.

## Qué demuestra

- Teoría musical en código: notas MIDI, temperamento igual, escalas/modos y
  tríadas diatónicas.
- **Cadena de Markov** sobre funciones tonales (T → S → D → T) con cadencia
  auténtica V → I garantizada al final.
- Reglas de conducción melódica: notas del acorde en tiempos fuertes, grado
  conjunto en los débiles, compensación de saltos, registro acotado y final en
  la tónica.
- Síntesis aditiva con envolvente ADSR, mezcla de pistas y normalización a -1 dBFS.
- Escritura de un MIDI estándar (formato 0, VLQ, meta-eventos de tempo) a mano.
- Generación **determinista** por semilla (mismo número → misma pieza).

## Arquitectura

```
musica/
├── teoria.py        # notas, frecuencias, Escala (grados, acordes, pertenencia)
├── composicion.py   # progresion() Markov + Compositor → Pieza (Nota: altura/inicio/duración)
├── sintesis.py      # envolvente, renderizar → np.ndarray, guardar_wav, a_midi
├── reproductor.py   # pygame (import perezoso)
└── cli.py
```

## Instalación y uso

```bash
pip install -e .              # numpy
pip install -e '.[audio]'     # + pygame para --reproducir

python -m musica --semilla 7 --tonica D --modo dorica --compases 16 --tempo 90 \
    --wav pieza.wav --midi pieza.mid --reproducir
```

Modos: `mayor`, `menor`, `dorica`, `mixolidia`, `pentatonica`. Tónicas en
notación inglesa (`C`, `F#`, `Bb`) o latina (`Do`, `Sol`, `La`).

## Tests

```bash
pip install pytest && python -m pytest
```

Verifican la teoría (acordes, grados, frecuencias), la cadencia de la
progresión, las reglas melódicas sobre varios modos y semillas (notas en la
escala, compases completos, tiempos fuertes en el acorde, final en la tónica,
mayoría de movimiento por grado conjunto), el determinismo, el WAV (cabecera y
duración exacta, sin saturar), el MIDI (cabeceras, VLQ, longitud de pista) y
la reproducción con el driver de audio `dummy` de SDL (sin placa de sonido).

## Limitaciones

- La armonía es diatónica simple: sin dominantes secundarias, modulaciones ni
  inversiones; en pentatónica los "acordes" son apilados de la propia escala.
- No hay conducción de voces entre acordes (todas las tríadas en estado fundamental).
- La síntesis es básica (3 armónicos fijos); para mejor sonido, abrí el `.mid`
  en un DAW o con un sintetizador como FluidSynth.
- Que la música "suene bien" es subjetivo: los tests comprueban reglas, no estética.
