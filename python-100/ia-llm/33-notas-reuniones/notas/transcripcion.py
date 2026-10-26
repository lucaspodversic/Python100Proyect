"""Interfaz de transcripción de audio y sus implementaciones.

- `TranscriptorWhisperAPI`: API de OpenAI (/audio/transcriptions), clave por env.
- `TranscriptorWhisperLocal`: paquete `openai-whisper` (opcional, corre local).
- `TranscriptorFalso`: devuelve segmentos fijos -> tests deterministas sin audio.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx


@dataclass(frozen=True)
class Segmento:
    inicio: float      # segundos
    fin: float
    texto: str
    hablante: str = "?"


class Transcriptor(Protocol):
    def transcribir(self, ruta_audio: str | Path) -> list[Segmento]: ...


def separar_hablante(texto: str) -> tuple[str, str]:
    """Si el texto empieza con 'Nombre: ...', separa el hablante (diarización simple)."""
    # Nombre con mayúscula inicial, 2 a 21 letras, seguido de ":". Así "Nota:
    # algo" también matchearía: es una diarización simple, no un modelo real.
    m = re.match(r"^\s*([A-ZÁÉÍÓÚÑ][\wáéíóúñ]{1,20}):\s*(.+)$", texto, re.S)
    return (m.group(1), m.group(2).strip()) if m else ("?", texto.strip())


class TranscriptorWhisperAPI:
    def __init__(self, cliente: httpx.Client | None = None, modelo: str = "whisper-1") -> None:
        self._cliente, self.modelo = cliente, modelo

    def transcribir(self, ruta_audio: str | Path) -> list[Segmento]:
        clave = os.environ.get("OPENAI_API_KEY")
        if not clave:
            raise RuntimeError("Falta OPENAI_API_KEY")
        # Timeout largo: transcribir un audio de una hora puede tardar minutos.
        cliente = self._cliente or httpx.Client(timeout=300)
        ruta = Path(ruta_audio)
        r = cliente.post("https://api.openai.com/v1/audio/transcriptions",
                         headers={"Authorization": f"Bearer {clave}"},
                         # verbose_json trae segmentos con tiempos; fijar el idioma mejora precisión.
                         data={"model": self.modelo, "response_format": "verbose_json", "language": "es"},
                         files={"file": (ruta.name, ruta.read_bytes())})
        r.raise_for_status()
        segs = []
        for s in r.json().get("segments", []):
            hablante, texto = separar_hablante(s["text"])
            segs.append(Segmento(float(s["start"]), float(s["end"]), texto, hablante))
        return segs


class TranscriptorWhisperLocal:  # pragma: no cover - requiere el modelo descargado
    def __init__(self, modelo: str = "base") -> None:
        import whisper  # import perezoso: dependencia opcional y pesada
        self._modelo = whisper.load_model(modelo)

    def transcribir(self, ruta_audio: str | Path) -> list[Segmento]:
        res = self._modelo.transcribe(str(ruta_audio), language="es")
        # separar_hablante devuelve (hablante, texto); Segmento espera (texto,
        # hablante): de ahí el reversed.
        return [Segmento(s["start"], s["end"], *reversed(separar_hablante(s["text"]))) for s in res["segments"]]


class TranscriptorFalso:
    """Lee los segmentos de un JSON (fixture) o de una lista dada."""

    def __init__(self, segmentos: list[Segmento] | None = None, fixture: str | Path | None = None) -> None:
        if fixture:
            segmentos = [Segmento(**s) for s in json.loads(Path(fixture).read_text(encoding="utf-8"))]
        self.segmentos = segmentos or []

    def transcribir(self, ruta_audio: str | Path) -> list[Segmento]:
        # Copia: quien llama puede modificar la lista sin afectar al falso.
        return list(self.segmentos)
