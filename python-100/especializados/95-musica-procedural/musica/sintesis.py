"""Síntesis aditiva sencilla → WAV, y exportación MIDI (formato 0), sin dependencias externas salvo numpy.

Cada nota se sintetiza como una onda con armónicos (1, 1/2, 1/4) y una
envolvente ADSR lineal, para evitar los "clics" al empezar y terminar. Las
pistas se mezclan con ganancias distintas y el resultado se normaliza a -1 dBFS
para que no sature.
"""
from __future__ import annotations

import struct
import wave
from pathlib import Path

import numpy as np

from .composicion import Nota, Pieza
from .teoria import frecuencia

TASA = 22_050
ARMONICOS = ((1, 1.0), (2, 0.5), (3, 0.25))
GANANCIA_PISTA = (0.9, 0.35, 0.6)  # melodía, acordes, bajo
PICO = 10 ** (-1 / 20)            # -1 dBFS


def envolvente(n: int, tasa: int = TASA, a: float = 0.01, d: float = 0.08, s: float = 0.7, r: float = 0.08) -> np.ndarray:
    """ADSR en muestras; si la nota es corta, ataque y relajación se reducen proporcionalmente."""
    ia, idd, ir = int(a * tasa), int(d * tasa), int(r * tasa)
    escala = min(1.0, n / max(1, ia + idd + ir))
    ia, idd, ir = int(ia * escala), int(idd * escala), int(ir * escala)
    sus = max(0, n - ia - idd - ir)
    env = np.concatenate([np.linspace(0, 1, ia, endpoint=False), np.linspace(1, s, idd, endpoint=False),
                          np.full(sus, s), np.linspace(s, 0, ir)])
    return env[:n] if len(env) >= n else np.pad(env, (0, n - len(env)))


def sintetizar_nota(nota: Nota, seg_por_tiempo: float, tasa: int = TASA) -> np.ndarray:
    """Suma de senos con algunos armónicos (timbre parecido a un órgano suave), descartando los
    que superan Nyquist (tasa/2) para que no haya aliasing. Se multiplica por una
    envolvente ADSR y se escala por la velocidad.
    """
    n = max(1, int(nota.duracion * seg_por_tiempo * tasa))
    t = np.arange(n) / tasa
    f = frecuencia(nota.altura)
    onda = sum(amp * np.sin(2 * np.pi * f * k * t) for k, amp in ARMONICOS if f * k < tasa / 2)  # evita aliasing
    return onda * envolvente(n, tasa) * (nota.velocidad / 127)


def renderizar(pieza: Pieza, tasa: int = TASA) -> np.ndarray:
    """Mezcla todas las pistas en un array float en [-1, 1]."""
    spt = 60 / pieza.tempo
    total = int((pieza.tiempos * spt + 0.5) * tasa)  # medio segundo de cola
    mezcla = np.zeros(total)
    for pista, gan in zip(pieza.pistas(), GANANCIA_PISTA):
        for nota in pista:
            señal = sintetizar_nota(nota, spt, tasa) * gan
            i = int(nota.inicio * spt * tasa)
            fin = min(total, i + len(señal))
            mezcla[i:fin] += señal[: fin - i]
    pico = float(np.max(np.abs(mezcla))) or 1.0
    return mezcla / pico * PICO


def a_pcm16(señal: np.ndarray) -> bytes:
    """Recorta a [-1, 1] y convierte a enteros de 16 bits little-endian, el formato de un WAV
    PCM.
    """
    return (np.clip(señal, -1, 1) * 32767).astype("<i2").tobytes()


def guardar_wav(señal: np.ndarray, ruta: Path, tasa: int = TASA) -> Path:
    """WAV mono de 16 bits a la tasa dada, con la librería estándar ``wave``."""
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(tasa)
        w.writeframes(a_pcm16(señal))
    return ruta


# ---------------- MIDI ----------------
PPQ = 480  # pulsos por negra


def _vlq(n: int) -> bytes:
    """Cantidad de longitud variable (7 bits por byte, MSB = continúa)."""
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    return bytes(reversed(out))


def a_midi(pieza: Pieza) -> bytes:
    """Archivo MIDI estándar de formato 0. Melodía en el canal 0, acordes en el 1 y bajo en el 2."""
    eventos: list[tuple[int, int, bytes]] = []  # (tick, orden, datos); orden: note-off antes que note-on
    for canal, (pista, programa) in enumerate(zip(pieza.pistas(), (0, 48, 32))):  # piano, cuerdas, bajo acústico
        eventos.append((0, 0, bytes([0xC0 | canal, programa])))
        for n in pista:
            ini, fin = round(n.inicio * PPQ), round((n.inicio + n.duracion) * PPQ)
            eventos.append((ini, 2, bytes([0x90 | canal, n.altura, n.velocidad])))
            eventos.append((fin, 1, bytes([0x80 | canal, n.altura, 0])))
    eventos.sort(key=lambda e: (e[0], e[1]))
    mpqn = round(60_000_000 / pieza.tempo)  # microsegundos por negra
    datos = bytearray(b"\x00\xff\x51\x03" + mpqn.to_bytes(3, "big"))
    previo = 0
    for tick, _, ev in eventos:
        datos += _vlq(tick - previo) + ev
        previo = tick
    datos += b"\x00\xff\x2f\x00"  # fin de pista
    return b"MThd" + struct.pack(">IHHH", 6, 0, 1, PPQ) + b"MTrk" + struct.pack(">I", len(datos)) + bytes(datos)
