"""Page Objects del portal (mock).

Cada clase encapsula los selectores y acciones de una página. Si el HTML
cambia, sólo se tocan estas clases; el bot y las reglas quedan intactos.
"""

from __future__ import annotations

from .navegador import Navegador
from .perfil import Oferta, Perfil


def _entero(texto: str) -> int | None:
    """Extrae un entero de textos como ``"USD 3.500"``; ``None`` si no hay dígitos."""
    # "USD 3.500" → "3500": se descartan moneda y separadores de miles.
    digitos = "".join(c for c in texto if c.isdigit())
    return int(digitos) if digitos else None


class PaginaListado:
    """Listado paginado de ofertas: ``/ofertas?pagina=N``."""

    # Selector centralizado: si cambia el HTML del portal, se ajusta sólo aquí.
    TARJETA = "article.oferta"

    def __init__(self, nav: Navegador) -> None:
        self.nav = nav

    def ofertas(self) -> list[tuple[Oferta, str]]:
        """Devuelve (oferta resumida, URL de detalle) por cada tarjeta."""
        resultado: list[tuple[Oferta, str]] = []
        for i, _ in enumerate(self.nav.buscar(self.TARJETA)):
            # Buscamos los hijos por índice para no depender de Elemento.buscar.
            sel = f"{self.TARJETA}:nth-of-type({i + 1})"
            tarjeta = self.nav.buscar(sel)[0]
            oid = tarjeta.atributo("data-id") or ""
            titulo = self.nav.buscar(f"{sel} .titulo")[0].texto
            empresa = self.nav.buscar(f"{sel} .empresa")[0].texto
            ubicacion = self.nav.buscar(f"{sel} .ubicacion")[0].texto
            modalidad = self.nav.buscar(f"{sel} .modalidad")[0].texto
            # El salario es opcional en el sitio: si no hay elemento, queda None ("no informado").
            sal = self.nav.buscar(f"{sel} .salario")
            enlace = self.nav.buscar(f"{sel} a.ver")[0].atributo("href") or ""
            oferta = Oferta(oid, titulo, empresa, ubicacion, modalidad, _entero(sal[0].texto) if sal else None)
            resultado.append((oferta, enlace))
        return resultado

    def hay_siguiente(self) -> bool:
        # Sin enlace "Siguiente" estamos en la última página.
        return bool(self.nav.buscar("a.siguiente"))

    def ir_siguiente(self) -> None:
        self.nav.buscar("a.siguiente")[0].clic()


class PaginaOferta:
    """Detalle de una oferta: descripción + botón Postular."""

    def __init__(self, nav: Navegador) -> None:
        self.nav = nav

    def descripcion(self) -> str:
        return self.nav.buscar(".descripcion")[0].texto

    def ya_postulado(self) -> bool:
        # Indicador del propio sitio de que ya existe una postulación a esta oferta.
        return bool(self.nav.buscar(".ya-postulado"))

    def abrir_formulario(self) -> "PaginaFormulario":
        self.nav.buscar("a.postular")[0].clic()
        return PaginaFormulario(self.nav)


class PaginaFormulario:
    """Formulario de postulación."""

    def __init__(self, nav: Navegador) -> None:
        self.nav = nav

    def completar_y_enviar(self, perfil: Perfil) -> bool:
        """Completa los campos y envía; devuelve ``True`` si hubo confirmación."""
        # Se completan sólo los campos visibles; los ocultos (token) los toma el navegador del HTML.
        self.nav.buscar("form#postulacion input[name=nombre]")[0].escribir(perfil.nombre)
        self.nav.buscar("form#postulacion input[name=email]")[0].escribir(perfil.email)
        self.nav.buscar("form#postulacion textarea[name=carta]")[0].escribir(perfil.carta)
        self.nav.buscar("form#postulacion button[type=submit]")[0].clic()
        # El éxito se valida por el mensaje de confirmación, no por el código HTTP.
        return bool(self.nav.buscar(".confirmacion"))
