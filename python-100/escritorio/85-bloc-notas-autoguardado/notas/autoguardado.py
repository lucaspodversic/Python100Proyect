"""Política de autoguardado, pura y testeable con un reloj falso.

Combina dos reglas:

* **debounce**: guardar cuando el usuario deja de escribir ``espera`` segundos;
* **plazo máximo**: si escribe sin parar, guardar igual cada ``maximo``
  segundos para no perder demasiado ante un corte.

La GUI llama a :meth:`marcar_cambio` en cada tecla y consulta
:meth:`debe_guardar` periódicamente con ``after``.
"""
from __future__ import annotations

import time
from collections.abc import Callable


class Autoguardado:
    """Decide *cuándo* guardar, sin temporizadores propios (la GUI lo consulta periódicamente).

    Combina dos reglas:

    * **debounce**: guardar cuando pasaron ``espera`` segundos desde el último
      cambio (el usuario hizo una pausa);
    * **plazo máximo**: si escribe sin parar, guardar igual a los ``maximo``
      segundos del primer cambio sin guardar, para no arriesgar demasiado texto.

    El reloj es inyectable, así los tests simulan el tiempo sin dormir.
    """

    def __init__(self, espera: float = 1.5, maximo: float = 10.0,
                 reloj: Callable[[], float] = time.monotonic) -> None:
        """Valida 0 < espera <= maximo (un plazo máximo menor que la espera no tendría
        sentido).
        """
        if espera <= 0 or maximo < espera:
            raise ValueError("se requiere 0 < espera <= maximo")
        self.espera, self.maximo, self.reloj = espera, maximo, reloj
        self._primer_cambio: float | None = None  # inicio de la racha sin guardar
        self._ultimo_cambio: float | None = None

    @property
    def pendiente(self) -> bool:
        """True si hay cambios todavía no guardados."""
        return self._primer_cambio is not None

    def marcar_cambio(self) -> None:
        """Registra una edición: la primera de la racha fija el inicio (para el plazo máximo);
        todas renuevan el último cambio (para el debounce).
        """
        t = self.reloj()
        if self._primer_cambio is None:
            self._primer_cambio = t
        self._ultimo_cambio = t

    def debe_guardar(self) -> bool:
        """True si se cumple alguna de las dos reglas (pausa suficiente o plazo máximo)."""
        if self._primer_cambio is None or self._ultimo_cambio is None:
            return False
        t = self.reloj()
        return t - self._ultimo_cambio >= self.espera or t - self._primer_cambio >= self.maximo

    def guardado(self) -> None:
        """Llamar tras guardar con éxito: reinicia la racha."""
        self._primer_cambio = self._ultimo_cambio = None
