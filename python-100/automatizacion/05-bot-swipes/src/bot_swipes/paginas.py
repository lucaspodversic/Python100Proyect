"""Page Object de la pantalla de perfiles."""

from __future__ import annotations

from .navegador import Navegador
from .preferencias import Perfil


class PaginaPerfiles:
    """Encapsula selectores y acciones de la pantalla de swipe."""

    def __init__(self, nav: Navegador) -> None:
        self.nav = nav

    def hay_perfil(self) -> bool:
        # Cuando no quedan perfiles, la app muestra ".sin-perfiles" en lugar de la sección.
        return bool(self.nav.buscar("section.perfil"))

    def perfil_actual(self) -> Perfil:
        """Lee la tarjeta visible y la convierte en ``Perfil``."""
        sec = self.nav.buscar("section.perfil")[0]
        # "a 5 km" → "5": se conservan dígitos y punto decimal. Sin dígitos → 0 km.
        dist = "".join(c for c in self.nav.buscar(".distancia")[0].texto if c.isdigit() or c == ".")
        return Perfil(
            id=sec.atributo("data-id") or "",
            nombre=self.nav.buscar(".nombre")[0].texto,
            edad=int(self.nav.buscar(".edad")[0].texto),
            distancia_km=float(dist or 0),
            bio=self.nav.buscar(".bio")[0].texto,
            # Lista vacía si el perfil no declara intereses.
            intereses=[e.texto for e in self.nav.buscar("ul.intereses li")],
        )

    def like(self) -> bool:
        """Da like; devuelve ``True`` si la app anunció un match."""
        # El clic en el botón envía el formulario f-like; la respuesta ya trae el siguiente perfil
        # y, si hubo match, el aviso ".match".
        self.nav.buscar("button.like")[0].clic()
        return bool(self.nav.buscar(".match"))

    def pasar(self) -> None:
        self.nav.buscar("button.pass")[0].clic()
