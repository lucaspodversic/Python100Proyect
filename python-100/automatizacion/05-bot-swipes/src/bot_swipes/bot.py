"""Orquestador con límites: dry-run, likes máximos, pausa entre swipes."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlsplit

from .navegador import Navegador
from .paginas import PaginaPerfiles
from .preferencias import Perfil, Preferencias, Veredicto, decidir

# Lista blanca de hosts loopback: cualquier otro destino (incluida una app real) se rechaza.
HOSTS_LOCALES = {"127.0.0.1", "localhost", "::1"}


@dataclass
# Registro de cada acción para el log/auditoría: qué perfil, qué se decidió y si hubo match.
class Swipe:
    perfil: Perfil
    veredicto: Veredicto
    ejecutado: bool  # False en dry-run
    match: bool = False


@dataclass
# Valores por defecto conservadores: dry-run activado, tope de likes y pausa de 2 s entre swipes.
class BotSwipes:
    nav: Navegador
    prefs: Preferencias
    url: str
    dry_run: bool = True
    max_likes: int = 20
    max_perfiles: int = 100
    pausa: float = 2.0
    dormir: Callable[[float], None] = time.sleep

    def __post_init__(self) -> None:
        # Seguridad: el bot sólo opera contra el mock local.
        if (urlsplit(self.url).hostname or "") not in HOSTS_LOCALES:
            raise ValueError("Sólo se permite la app mock en 127.0.0.1/localhost")

    def ejecutar(self) -> list[Swipe]:
        """En dry-run sólo evalúa el perfil visible (no puede avanzar sin swipear)."""
        self.nav.ir(self.url)
        pagina = PaginaPerfiles(self.nav)
        historial: list[Swipe] = []
        likes = 0
        # Dos cortes: la app no tiene más perfiles o se alcanzó el tope de perfiles por corrida.
        while pagina.hay_perfil() and len(historial) < self.max_perfiles:
            perfil = pagina.perfil_actual()
            # La decisión la toman las reglas puras de ``preferencias``; el bot sólo ejecuta.
            v = decidir(perfil, self.prefs)
            if v.like and likes >= self.max_likes:
                # Alcanzado el límite diario de likes: paramos en lugar de pasar.
                break
            # En dry-run no se puede "avanzar" sin swipear (la app sólo muestra el perfil actual),
            # así que se evalúa el primero y se termina.
            if self.dry_run:
                historial.append(Swipe(perfil, v, ejecutado=False))
                break
            # Pausa antes de cada acción real (rate limiting); inyectable para los tests.
            self.dormir(self.pausa)
            match = False
            if v.like:
                # El like devuelve si la app anunció match; sólo los likes cuentan para el tope.
                match = pagina.like()
                likes += 1
            else:
                pagina.pasar()
            historial.append(Swipe(perfil, v, ejecutado=True, match=match))
        return historial
