"""Lado del votante (lo que correría en su dispositivo, nunca en el servidor).

Mantiene en secreto la serie, la opción y el factor ``r`` hasta descegar.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass, field

from .cripto import ClavePublica, cegar, descegar, factor_cegado, verificar
from .servicio import mensaje_papeleta


@dataclass
class Votante:
    publica: ClavePublica
    eleccion: str
    opcion: str
    # Serie aleatoria de 256 bits: la probabilidad de colisión entre votantes es despreciable.
    serie: str = field(default_factory=lambda: secrets.token_hex(32))
    _r: int = field(init=False, repr=False)  # factor de cegado: si se filtra, se puede vincular el voto

    def __post_init__(self) -> None:
        self._r = factor_cegado(self.publica.n)

    @property
    def mensaje(self) -> bytes:
        return mensaje_papeleta(self.eleccion, self.serie, self.opcion)

    def cegado(self) -> int:
        """Valor que se envía a la autoridad junto con el token."""
        return cegar(self.publica, self.mensaje, self._r)

    def papeleta(self, firma_cegada: int) -> dict:
        """Desciega, verifica localmente (detecta una autoridad tramposa) y arma el voto anónimo."""
        firma = descegar(self.publica, firma_cegada, self._r)
        if not verificar(self.publica, self.mensaje, firma):
            raise ValueError("la autoridad devolvió una firma inválida")
        return {"serie": self.serie, "opcion": self.opcion, "firma": format(firma, "x")}
