"""Conversión texto → audio con un motor de voz intercambiable.

`MotorVoz` es la interfaz; `MotorGTTS` la implementación real (necesita
internet porque gTTS usa el servicio de Google). Los tests usan un fake.
Los MP3 de cada trozo se concatenan: el formato MP3 es una secuencia de
frames independientes, por lo que concatenar bytes produce un archivo
reproducible (técnica estándar para gTTS).
"""
from __future__ import annotations

import io
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from .texto import extraer_texto, limpiar_texto, trocear

# Logger propio para los avisos de reintento.
log = logging.getLogger("audiolibro")


# Interfaz estructural: cualquier objeto con sintetizar(texto, idioma) -> bytes sirve.
class MotorVoz(Protocol):
    def sintetizar(self, texto: str, idioma: str) -> bytes:
        """Devuelve audio MP3 para `texto`."""
        ...


class MotorGTTS:
    """Motor real basado en gTTS (import perezoso: dependencia opcional)."""

    def __init__(self, lento: bool = False):
        self.lento = lento

    def sintetizar(self, texto: str, idioma: str) -> bytes:
        # Import perezoso: el resto del paquete (y los tests) funcionan sin gTTS instalado.
        from gtts import gTTS  # sólo se importa si se usa de verdad

        # Se escribe en memoria y se devuelven los bytes: el Convertidor decide dónde guardarlos.
        buf = io.BytesIO()
        gTTS(text=texto, lang=idioma, slow=self.lento).write_to_fp(buf)
        return buf.getvalue()


@dataclass
class Convertidor:
    """Orquesta extracción, troceo y síntesis con reintentos."""
    motor: MotorVoz
    idioma: str = "es"
    # Trozos de hasta 500 caracteres: gTTS funciona mejor con fragmentos cortos.
    max_trozo: int = 500
    reintentos: int = 3
    pausa_reintento: float = 2.0
    # Inyectable para que los tests no esperen de verdad entre reintentos.
    dormir: Callable[[float], None] = time.sleep

    def _sintetizar_con_reintentos(self, trozo: str) -> bytes:
        """El servicio remoto puede fallar puntualmente: reintentamos con espera creciente."""
        # Intentos numerados desde 1 para que la espera crezca linealmente: 2 s, 4 s, ...
        for intento in range(1, self.reintentos + 1):
            try:
                return self.motor.sintetizar(trozo, self.idioma)
            except Exception as exc:
                # Último intento: se propaga la excepción original al llamador.
                if intento == self.reintentos:
                    raise
                log.warning("Fallo TTS (intento %d): %s", intento, exc)
                self.dormir(self.pausa_reintento * intento)
        # Sólo se llegaría con reintentos <= 0 (el bucle no corre ninguna vez).
        raise AssertionError("inalcanzable")

    def texto_a_mp3(self, texto: str, destino: Path, progreso: Callable[[int, int], None] | None = None) -> int:
        """Convierte texto a un MP3. Devuelve cuántos trozos se sintetizaron."""
        # Primero se normaliza el texto y luego se divide en trozos aptos para el TTS.
        trozos = trocear(limpiar_texto(texto), self.max_trozo)
        # Caso borde: PDF escaneado (imágenes) o páginas vacías → no hay nada que leer.
        if not trozos:
            raise ValueError("No hay texto para convertir (¿PDF escaneado sin OCR?)")
        destino.parent.mkdir(parents=True, exist_ok=True)
        # Se escribe trozo a trozo: no se acumula todo el audio en memoria.
        with open(destino, "wb") as f:
            for i, t in enumerate(trozos, start=1):
                f.write(self._sintetizar_con_reintentos(t))
                if progreso:
                    progreso(i, len(trozos))
        return len(trozos)

    def pdf_a_mp3(self, pdf: Path, destino: Path, desde: int = 1, hasta: int | None = None,
                  por_pagina: bool = False) -> list[Path]:
        """Convierte un PDF; con `por_pagina` genera un MP3 por página (capítulos)."""
        # Lista con el texto de cada página del rango.
        paginas = extraer_texto(pdf, desde, hasta)
        if not por_pagina:
            # Modo único: las páginas se unen como párrafos en un solo MP3.
            self.texto_a_mp3("\n\n".join(paginas), destino)
            return [destino]
        salidas = []
        # start=desde: el número del archivo coincide con la página real del PDF.
        for n, texto in enumerate(paginas, start=desde):
            # Las páginas en blanco se saltean (no se genera un MP3 vacío).
            if limpiar_texto(texto):
                # libro.mp3 → libro_p001.mp3, libro_p002.mp3... (3 dígitos para ordenar bien).
                ruta = destino.with_name(f"{destino.stem}_p{n:03d}{destino.suffix}")
                self.texto_a_mp3(texto, ruta)
                salidas.append(ruta)
        return salidas
