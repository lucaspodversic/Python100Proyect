# 51 · Convertidor de PDF a audiolibro

Extrae el texto de un PDF y lo convierte a voz (MP3) con **gTTS**.

## Qué demuestra
- Extracción de texto con `pypdf` por rango de páginas.
- Limpieza para lectura en voz alta (palabras cortadas con guion, saltos de línea).
- Troceado por oraciones respetando el límite del servicio de voz.
- Motor de voz **intercambiable** (`MotorVoz`), reintentos con espera creciente.
- Modo "un MP3 por página" (capítulos).

## Arquitectura
```
audiolibro/
  texto.py        # extraer_texto, limpiar_texto, trocear
  convertidor.py  # MotorVoz, MotorGTTS, Convertidor (texto_a_mp3, pdf_a_mp3)
  cli.py
```

## Instalación
```bash
pip install -e ".[dev,tts]"   # 'tts' instala gTTS
```

## Uso
```bash
python -m audiolibro libro.pdf -o libro.mp3
python -m audiolibro libro.pdf --desde 5 --hasta 20 --por-pagina --idioma es
```

## Tests
```bash
pytest
```
Los tests generan un PDF en memoria y usan un motor de voz falso (sin internet).

## Limitaciones
- gTTS usa un servicio no oficial de Google: requiere internet y puede cambiar o limitar pedidos.
  Alternativa offline: implementar `MotorVoz` con `pyttsx3` o Piper.
- PDFs escaneados (imágenes) necesitan OCR previo (p. ej. `ocrmypdf`).
