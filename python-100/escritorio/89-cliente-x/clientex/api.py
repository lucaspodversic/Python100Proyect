"""Acceso a la API oficial de X (v2) detrás de una interfaz.

* :class:`ServicioX` (Protocol) es lo único que conocen el controlador y la GUI.
* :class:`ClienteXAPI` habla con ``https://api.x.com/2`` mediante ``httpx``.
  El token se lee de una **variable de entorno**, nunca del código ni de un
  archivo del repositorio.
* :class:`ServicioFalso` vive en memoria para tests y demos sin red.

Endpoints usados (documentación oficial de X API v2):

* ``GET  /2/users/me`` — usuario autenticado.
* ``GET  /2/users/:id/tweets`` — publicaciones de un usuario.
* ``GET  /2/tweets/search/recent`` — búsqueda de los últimos 7 días.
* ``POST /2/tweets`` — publicar (requiere token de **usuario** OAuth 2.0 con
  ``tweet.write``; un *Bearer* de app solo sirve para leer).
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Protocol

import httpx

URL_BASE = "https://api.x.com/2"
VAR_TOKEN = "X_BEARER_TOKEN"            # lectura (app-only) o token de usuario
VAR_TOKEN_USUARIO = "X_USER_ACCESS_TOKEN"  # opcional: OAuth 2.0 de usuario para publicar


class ErrorX(Exception):
    """Error de la API con mensaje para el usuario."""


class ErrorAutenticacion(ErrorX):
    """Token ausente, inválido, vencido o sin permisos (401/403)."""
    pass


class ErrorLimite(ErrorX):
    """429: se superó el límite; ``espera`` = segundos hasta el reinicio."""

    def __init__(self, espera: int) -> None:
        """``espera``: segundos hasta que X vuelva a aceptar peticiones (sale de x-rate-limit-
        reset).
        """
        super().__init__(f"límite de peticiones alcanzado; reintentá en {espera} s")
        self.espera = espera


@dataclass(frozen=True)
class Post:
    """Una publicación ya normalizada: el autor se resuelve de ``includes.users`` y los me
    gusta de ``public_metrics``.
    """
    id: str
    texto: str
    autor: str = ""
    fecha: str = ""
    me_gusta: int = 0


@dataclass
class Pagina:
    """Un lote de posts más el token para pedir el siguiente (None = no hay más)."""
    posts: list[Post]
    siguiente: str | None = None  # next_token para paginar


class ServicioX(Protocol):
    """Lo que la app necesita de X. Lo cumplen ``ClienteXAPI`` (red real) y ``ServicioFalso`` (tests y modo demo)."""

    def yo(self) -> dict[str, str]:
        """Datos del usuario autenticado (id y username)."""
        ...

    def publicaciones(self, usuario_id: str, cursor: str | None = None) -> Pagina:
        """Publicaciones de un usuario, paginadas con ``cursor``."""
        ...

    def buscar(self, consulta: str, cursor: str | None = None) -> Pagina:
        """Búsqueda reciente, paginada con ``cursor``."""
        ...

    def publicar(self, texto: str, responde_a: str | None = None) -> Post:
        """Publica un post, opcionalmente como respuesta (para armar hilos)."""
        ...


def _a_posts(datos: dict) -> Pagina:
    """Convierte la respuesta JSON de la API (con ``expansions=author_id``) en una Pagina."""
    usuarios = {u["id"]: u.get("username", "") for u in datos.get("includes", {}).get("users", [])}
    posts = [Post(id=d["id"], texto=d.get("text", ""), autor=usuarios.get(d.get("author_id", ""), ""),
                  fecha=d.get("created_at", ""), me_gusta=d.get("public_metrics", {}).get("like_count", 0))
             for d in datos.get("data", [])]
    return Pagina(posts, datos.get("meta", {}).get("next_token"))


class ClienteXAPI:
    """Implementación real. ``transporte`` permite inyectar ``httpx.MockTransport`` en tests."""

    CAMPOS = {"tweet.fields": "created_at,public_metrics,author_id", "expansions": "author_id",
              "user.fields": "username", "max_results": "20"}

    def __init__(self, token: str | None = None, transporte: httpx.BaseTransport | None = None,
                 reloj=time.time) -> None:
        """Toma el token del argumento o del entorno (nunca de un archivo del repo).
        ``transporte`` permite inyectar un MockTransport en tests y ``reloj`` hace
        determinista el cálculo de espera ante un 429.
        """
        token = token or os.environ.get(VAR_TOKEN_USUARIO) or os.environ.get(VAR_TOKEN)
        if not token:
            raise ErrorAutenticacion(f"definí la variable de entorno {VAR_TOKEN} (o {VAR_TOKEN_USUARIO})")
        self._http = httpx.Client(base_url=URL_BASE, headers={"Authorization": f"Bearer {token}"},
                                  timeout=15, transport=transporte)
        self._reloj = reloj

    def __repr__(self) -> str:  # nunca mostrar el token en logs/tracebacks
        """Oculta el token: así no aparece en logs ni tracebacks."""
        return "ClienteXAPI(token=***)"

    def _pedir(self, metodo: str, ruta: str, **kw) -> dict:
        """Hace la petición y traduce errores a excepciones propias con mensajes en castellano:
        red → ErrorX; 401/403 → ErrorAutenticacion; 429 → ErrorLimite con la espera
        calculada desde el epoch de reinicio; otros ≥400 → ErrorX con el detalle de
        la API si lo hay.
        """
        try:
            r = self._http.request(metodo, ruta, **kw)
        except httpx.HTTPError as e:
            raise ErrorX(f"error de red: {e.__class__.__name__}") from e
        if r.status_code == 401:
            raise ErrorAutenticacion("token inválido o vencido")
        if r.status_code == 403:
            raise ErrorAutenticacion("el token no tiene permiso para esta acción (¿falta tweet.write?)")
        if r.status_code == 429:
            reinicio = int(r.headers.get("x-rate-limit-reset", "0") or 0)
            raise ErrorLimite(max(1, reinicio - int(self._reloj())))
        if r.status_code >= 400:
            try:
                detalle = r.json().get("detail") or r.json().get("title") or r.text
            except ValueError:
                detalle = r.text
            raise ErrorX(f"HTTP {r.status_code}: {str(detalle)[:200]}")
        return r.json()

    def yo(self) -> dict[str, str]:
        """GET /2/users/me."""
        return self._pedir("GET", "/users/me")["data"]

    def publicaciones(self, usuario_id: str, cursor: str | None = None) -> Pagina:
        """GET /2/users/:id/tweets; esta ruta pagina con ``pagination_token``."""
        params = dict(self.CAMPOS, **({"pagination_token": cursor} if cursor else {}))
        return _a_posts(self._pedir("GET", f"/users/{usuario_id}/tweets", params=params))

    def buscar(self, consulta: str, cursor: str | None = None) -> Pagina:
        """GET /2/tweets/search/recent (últimos 7 días); esta ruta pagina con ``next_token``.
        Una búsqueda vacía se rechaza antes de gastar una petición.
        """
        if not consulta.strip():
            raise ErrorX("búsqueda vacía")
        params = dict(self.CAMPOS, query=consulta, **({"next_token": cursor} if cursor else {}))
        return _a_posts(self._pedir("GET", "/tweets/search/recent", params=params))

    def publicar(self, texto: str, responde_a: str | None = None) -> Post:
        """POST /2/tweets; con ``responde_a`` se encadena como respuesta (así se arma un hilo)."""
        cuerpo: dict = {"text": texto}
        if responde_a:
            cuerpo["reply"] = {"in_reply_to_tweet_id": responde_a}
        d = self._pedir("POST", "/tweets", json=cuerpo)["data"]
        return Post(id=d["id"], texto=d.get("text", texto))


@dataclass
class ServicioFalso:
    """Servicio en memoria: sin red. Útil para tests y para probar la GUI (``--demo``)."""

    usuario: dict[str, str] = field(default_factory=lambda: {"id": "1", "username": "demo", "name": "Demo"})
    posts: list[Post] = field(default_factory=list)
    tam_pagina: int = 2
    fallo: Exception | None = None   # si se define, todas las llamadas lo lanzan

    def _check(self) -> None:
        """Simula una falla configurada (sin token, límite, etc.)."""
        if self.fallo:
            raise self.fallo

    def _paginar(self, lista: list[Post], cursor: str | None) -> Pagina:
        """Paginación simulada: el cursor es el índice de inicio como texto."""
        ini = int(cursor or 0)
        fin = ini + self.tam_pagina
        return Pagina(lista[ini:fin], str(fin) if fin < len(lista) else None)

    def yo(self) -> dict[str, str]:
        """Usuario simulado."""
        self._check()
        return self.usuario

    def publicaciones(self, usuario_id: str, cursor: str | None = None) -> Pagina:
        """Posts cuyo autor es el usuario simulado."""
        self._check()
        return self._paginar([p for p in self.posts if p.autor == self.usuario["username"]], cursor)

    def buscar(self, consulta: str, cursor: str | None = None) -> Pagina:
        """Filtra por texto sin distinguir mayúsculas."""
        self._check()
        return self._paginar([p for p in self.posts if consulta.lower() in p.texto.lower()], cursor)

    def publicar(self, texto: str, responde_a: str | None = None) -> Post:
        """Inserta al principio (lo más nuevo primero, como X) con id incremental."""
        self._check()
        post = Post(str(1000 + len(self.posts)), texto, self.usuario["username"])
        self.posts.insert(0, post)
        return post
