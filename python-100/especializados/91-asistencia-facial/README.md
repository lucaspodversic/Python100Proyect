# 91 · Control de asistencia por reconocimiento facial

Sistema que identifica a las personas registradas frente a una cámara y anota su **entrada y salida** en SQLite, con un informe de horas por día. El pipeline de visión es intercambiable:

- **real**: OpenCV + `face_recognition` (dlib);
- **sintético**: embeddings deterministas, para desarrollar y testear sin cámara y **sin datos biométricos reales**.

## Qué demuestra

- **Arquitectura por interfaces**: `Extractor` (Protocol) → `Galeria` (identificación) → `Sistema` (confirmación) → `Registro` (fichajes).
- **Identificación prudente**:
  - La distancia euclídea al centroide debe quedar bajo un umbral, **con margen** respecto a la segunda candidata.
  - Si no, el resultado es "desconocido" o "ambiguo", y es mejor un fichaje manual que uno equivocado.
- **Confirmación en N fotogramas consecutivos** antes de fichar, para evitar falsos positivos de un único fotograma.
- **Antirrebote** de 2 minutos, entrada y salida alternadas, y salida olvidada detectada en el informe.
- **Privacidad desde el diseño**: ver la sección siguiente.

## Consentimiento y datos biométricos ⚠️

Los datos biométricos usados para identificar a una persona son una **categoría especial** de datos personales:

- RGPD, art. 9, en la UE.
- Ley 25.326 en Argentina; la AAIP los considera datos sensibles.
- BIPA en Illinois, entre otras.

En el ámbito laboral, el consentimiento no suele considerarse libre por el desequilibrio de poder entre empleador y empleado. Antes de usar esto con personas reales:

1. **Base legal y evaluación de impacto (DPIA)**: consultá con quien lleve protección de datos en tu organización.
2. **Alternativa sin biometría**: tarjeta, PIN o fichaje manual, sin penalizar a quien no acepte.
3. **Consentimiento explícito y documentado**: `Galeria.registrar` **se niega** a registrar sin un `Consentimiento` (quién, cuándo, finalidad).
4. **Minimización**:
   - Solo se guardan embeddings (vectores), nunca fotos.
   - Hay retención limitada (`Registro.purgar`).
5. **Derecho de supresión**: `Sistema.olvidar(persona)` borra los vectores y los fichajes.
6. **Seguridad**:
   - La galería se guarda en JSON **sin cifrar** en esta demo. En producción, ciframos en reposo y restringimos el acceso.
   - Avisá con cartelería visible de que hay una cámara.
7. **Sesgos**: los modelos de reconocimiento facial tienen tasas de error distintas según el grupo demográfico. Medí los errores con tu población y ofrecé siempre una vía de corrección humana.

## Arquitectura

```
asistencia/
├── pipeline.py  # Cara, Extractor (Protocol), ExtractorFaceRecognition (opcional), ExtractorSintetico
├── galeria.py   # Consentimiento, Galeria (registrar/identificar/olvidar/guardar/cargar)
├── registro.py  # Registro SQLite: marcar, informe_dia, purgar, olvidar
├── sistema.py   # Sistema: confirmación por fotogramas + fichaje
└── camara.py    # bucle con webcam (OpenCV), opcional
```

## Instalación y uso

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"            # lógica + tests (solo numpy)
pip install -e ".[vision]"         # opcional: OpenCV + face_recognition (compila dlib; requiere cmake)
python -m asistencia.camara galeria.json asistencia.db
```

Para crear `galeria.json`:

1. Extraé 3 o más embeddings por persona con `ExtractorFaceRecognition().extraer(imagen)`.
2. Llamá a `Galeria.registrar(persona, muestras, consentimiento)`.
3. Guardá con `Galeria.guardar(ruta)`.

## Tests

```bash
pytest
```

- Solo se usan embeddings sintéticos: no hay cámara, modelos ni rostros reales.
- Cubren consentimiento obligatorio, muestras incoherentes, desconocidos y ambiguos, antirrebote, informe de horas, purga, supresión y confirmación por fotogramas.

## Limitaciones

- **No hay detección de vida (liveness)**: una foto impresa o una pantalla pueden engañar al sistema. Para uso real hacen falta cámaras IR o 3D, o pruebas de desafío.
- El umbral 0,6 es el típico de `face_recognition`; hay que calibrarlo con datos propios.
- La identificación es lineal sobre la galería (bien para cientos de personas; para miles, usá un índice ANN).
- No se procesan turnos nocturnos que crucen la medianoche: el fichaje del día siguiente empieza con una entrada.
