"""Controlador sin Tkinter: orquesta llamadas al servicio y mantiene el estado de la vista.

Las llamadas de red se ejecutan mediante un ``ejecutor`` inyectable: en la
GUI es un hilo (para no congelar la ventana); en tests es síncrono.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from .api import ErrorX, Pagina, Post, ServicioX
from .texto import dividir_en_hilo, validar

Ejecutor = Callable[[Callable[[], object], Callable[[object], None], Callable[[Exception], None]], None]


def ejecutor_sincrono(trabajo, al_terminar, al_fallar) -> None:
    """Ejecutor que corre el trabajo en el acto. Lo usan los tests; la GUI usa uno con hilos
    para no congelar la ventana mientras espera a la red.
    """
    try:
        resultado = trabajo()
    except Exception as e:  # se reenvía a la vista como mensaje
        al_fallar(e)
    else:
        al_terminar(resultado)


@dataclass
class Controlador:
    """Estado y acciones de la app, sin Tk: lista visible, cursor de paginación, modo (propias
    o búsqueda), mensaje de estado y si hay una operación en curso. La vista solo se
    redibuja cuando llama ``al_cambiar``.
    """
    servicio: ServicioX
    ejecutor: Ejecutor = ejecutor_sincrono
    al_cambiar: Callable[[], None] = lambda: None   # la vista se redibuja
    posts: list[Post] = field(default_factory=list)
    cursor: str | None = None
    modo: tuple[str, str] = ("propias", "")   # ("propias", "") o ("buscar", consulta)
    mensaje: str = ""
    usuario: dict[str, str] | None = None
    ocupado: bool = False

    def _lanzar(self, trabajo: Callable[[], object], ok: Callable[[object], None]) -> None:
        """Ejecuta ``trabajo`` con el ejecutor marcando 'ocupado'. Al terminar aplica ``ok``;
        si falla, muestra el mensaje (los ErrorX ya son legibles; otros solo
        muestran el tipo, sin detalles internos).
        """
        self.ocupado = True
        self.mensaje = "Cargando…"
        self.al_cambiar()

        def fin(r: object) -> None:
            """Éxito: libera 'ocupado', aplica el resultado y redibuja."""
            self.ocupado = False
            ok(r)
            self.al_cambiar()

        def error(e: Exception) -> None:
            """Falla: libera 'ocupado' y muestra el error."""
            self.ocupado = False
            self.mensaje = f"Error: {e}" if isinstance(e, ErrorX) else f"Error inesperado: {e.__class__.__name__}"
            self.al_cambiar()

        self.ejecutor(trabajo, fin, error)

    def conectar(self) -> None:
        """Valida el token pidiendo el usuario y luego carga sus posts."""
        def ok(u):
            """Guarda el usuario y encadena la carga de posts propios."""
            self.usuario = u
            self.mensaje = f"Conectado como @{u.get('username')}"
            self.cargar_propias()
        self._lanzar(self.servicio.yo, ok)

    def _cargar(self, pagina_fn: Callable[[], Pagina], anexar: bool) -> None:
        """Carga una página: reemplaza la lista (nueva consulta) o la extiende ('Cargar más')."""
        def ok(p):
            """Actualiza lista, cursor y mensaje ('hay más' si quedan páginas)."""
            self.posts = (self.posts + p.posts) if anexar else p.posts
            self.cursor = p.siguiente
            self.mensaje = f"{len(self.posts)} publicaciones" + (" (hay más)" if p.siguiente else "")
        self._lanzar(pagina_fn, ok)

    def cargar_propias(self) -> None:
        """Muestra los posts propios; exige estar conectado."""
        if not self.usuario:
            self.mensaje = "Primero conectá"
            self.al_cambiar()
            return
        self.modo = ("propias", "")
        uid = self.usuario["id"]
        self._cargar(lambda: self.servicio.publicaciones(uid), anexar=False)

    def buscar(self, consulta: str) -> None:
        """Nueva búsqueda: reinicia la lista y recuerda la consulta para 'Cargar más'."""
        self.modo = ("buscar", consulta)
        self._cargar(lambda: self.servicio.buscar(consulta), anexar=False)

    def mas(self) -> None:
        """Carga la página siguiente del modo actual."""
        if not self.cursor:
            return
        c = self.cursor
        if self.modo[0] == "buscar":
            self._cargar(lambda: self.servicio.buscar(self.modo[1], c), anexar=True)
        else:
            uid = self.usuario["id"]
            self._cargar(lambda: self.servicio.publicaciones(uid, c), anexar=True)

    def publicar(self, texto: str, como_hilo: bool = False) -> bool:
        """Publica un post (o un hilo encadenado). Devuelve False si no pasa la validación."""
        partes = dividir_en_hilo(texto) if como_hilo else [texto]
        try:
            for p in partes:
                validar(p)
        except ValueError as e:
            self.mensaje = str(e)
            self.al_cambiar()
            return False

        def trabajo() -> list[Post]:
            """Publica las partes en orden, cada una como respuesta de la anterior."""
            publicados: list[Post] = []
            for p in partes:
                # Cada parte responde a la anterior → se encadena como hilo.
                publicados.append(self.servicio.publicar(p, publicados[-1].id if publicados else None))
            return publicados

        def ok(publicados):
            """Agrega lo publicado arriba de la lista (más nuevo primero)."""
            self.posts = list(reversed(publicados)) + self.posts
            self.mensaje = f"Publicado ({len(publicados)})"
        self._lanzar(trabajo, ok)
        return True
