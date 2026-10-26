"""Reproducción con pygame (opcional). Se importa de forma perezosa."""
from __future__ import annotations

import numpy as np

from .sintesis import TASA


def reproducir(señal: np.ndarray, tasa: int = TASA, esperar: bool = True) -> None:
    """Reproduce la señal con pygame.mixer, convirtiéndola a PCM de 16 bits. Si el mixer se
    abre en estéreo, duplica el canal. pygame es opcional: sin él da un error que
    explica cómo instalarlo.
    """
    try:
        import pygame
    except ImportError as e:
        raise RuntimeError("instalá pygame para reproducir: pip install -e '.[audio]'") from e
    pygame.mixer.pre_init(frequency=tasa, size=-16, channels=1)
    pygame.mixer.init()
    try:
        pcm = (np.clip(señal, -1, 1) * 32767).astype(np.int16)
        # El mixer puede abrirse en estéreo aunque se pidan 1 canal: adaptamos la forma.
        canales = pygame.mixer.get_init()[2]
        if canales > 1:
            pcm = np.repeat(pcm[:, None], canales, axis=1)
        sonido = pygame.sndarray.make_sound(np.ascontiguousarray(pcm))
        canal = sonido.play()
        while esperar and canal.get_busy():
            pygame.time.wait(100)
    finally:
        if esperar:
            pygame.mixer.quit()
