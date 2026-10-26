"""Abstracción de navegador para que el bot no dependa de Selenium.

``Navegador`` define la mínima API que usan los Page Objects. Hay dos
implementaciones:

- ``SeleniumNavegador``: adapta un ``selenium.webdriver`` real (Chrome/Firefox).
- ``HttpNavegador``: "navegador" liviano basado en urllib + BeautifulSoup que
  sigue links y envía formularios HTML. Alcanza para el sitio mock (que no usa
  JavaScript) y permite tests end-to-end sin instalar un navegador.
"""

from __future__ import annotations

import urllib.parse
import urllib.request
from typing import Any, Protocol

from bs4 import BeautifulSoup, Tag


# Interfaz mínima común a WebElement (Selenium) y a nuestro elemento HTTP.
class Elemento(Protocol):
    """Elemento de la página."""

    @property
    def texto(self) -> str: ...

    def atributo(self, nombre: str) -> str | None: ...

    def clic(self) -> None: ...

    # Se limpia antes de escribir para reemplazar (no concatenar) el contenido previo del campo.
    def escribir(self, valor: str) -> None: ...


class Navegador(Protocol):
    """Operaciones de navegación usadas por los Page Objects."""

    def ir(self, url: str) -> None: ...

    @property
    def url_actual(self) -> str: ...

    def buscar(self, selector_css: str) -> list[Elemento]: ...


# --------------------------------------------------------------------------- Selenium
class _ElementoSelenium:
    """Envoltura de ``WebElement`` con la API en español."""

    def __init__(self, el: Any) -> None:
        self._el = el

    @property
    def texto(self) -> str:
        return str(self._el.text)

    def atributo(self, nombre: str) -> str | None:
        return self._el.get_attribute(nombre)

    def clic(self) -> None:
        self._el.click()

    def escribir(self, valor: str) -> None:
        self._el.clear()
        self._el.send_keys(valor)


class SeleniumNavegador:
    """Adaptador sobre un WebDriver de Selenium (inyectado desde afuera).

    Se usa la cadena ``"css selector"`` (valor de ``By.CSS_SELECTOR``) para no
    requerir importar selenium en este módulo.
    """

    def __init__(self, driver: Any) -> None:
        self.driver = driver

    def ir(self, url: str) -> None:
        self.driver.get(url)

    @property
    def url_actual(self) -> str:
        return str(self.driver.current_url)

    def buscar(self, selector_css: str) -> list[Elemento]:
        # find_elements (plural) devuelve [] si no hay coincidencias, en vez de lanzar excepción.
        return [_ElementoSelenium(e) for e in self.driver.find_elements("css selector", selector_css)]


# --------------------------------------------------------------------------- HTTP
class _ElementoHttp:
    """Elemento del ``HttpNavegador``: conoce su Tag y el navegador dueño."""

    def __init__(self, nav: "HttpNavegador", tag: Tag) -> None:
        self._nav, self._tag = nav, tag

    @property
    def texto(self) -> str:
        return self._tag.get_text(" ", strip=True)

    def atributo(self, nombre: str) -> str | None:
        v = self._tag.get(nombre)
        # BeautifulSoup devuelve "class" como lista de clases; la unimos como haría un navegador.
        return " ".join(v) if isinstance(v, list) else v

    def escribir(self, valor: str) -> None:
        # Guardamos el valor en el estado del formulario del navegador.
        nombre = self.atributo("name")
        if nombre:
            self._nav._valores[nombre] = valor

    def clic(self) -> None:
        # Link: navegamos. Botón submit: enviamos su formulario.
        if self._tag.name == "a" and self._tag.get("href"):
            self._nav.ir(urllib.parse.urljoin(self._nav.url_actual, str(self._tag["href"])))
        elif self._tag.name in ("button", "input"):
            form = self._tag.find_parent("form")
            if form is not None:
                self._nav._enviar_formulario(form)


class HttpNavegador:
    """Navegador sin JavaScript para sitios HTML simples (como el mock)."""

    def __init__(self, user_agent: str = "BotPostulacionesDemo/1.0") -> None:
        self.user_agent = user_agent
        # Estado inicial equivalente a una pestaña vacía.
        self._url = "about:blank"
        self._sopa = BeautifulSoup("", "html.parser")
        # Valores "tipeados" por el usuario, pendientes de enviar con el próximo submit.
        self._valores: dict[str, str] = {}

    def _pedir(self, url: str, datos: bytes | None = None) -> None:
        req = urllib.request.Request(url, data=datos, headers={"User-Agent": self.user_agent})
        # ``geturl()`` devuelve la URL final tras redirecciones (como la barra de direcciones).
        with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310 - sólo URLs locales
            self._url = r.geturl()
            self._sopa = BeautifulSoup(r.read().decode("utf-8"), "html.parser")
        # Al cargar una página nueva se descartan los valores del formulario anterior.
        self._valores = {}

    def ir(self, url: str) -> None:
        self._pedir(url)

    @property
    def url_actual(self) -> str:
        return self._url

    def buscar(self, selector_css: str) -> list[Elemento]:
        return [_ElementoHttp(self, t) for t in self._sopa.select(selector_css)]

    def _enviar_formulario(self, form: Tag) -> None:
        """Serializa los campos del form (valores por defecto + escritos) y lo envía."""
        campos: dict[str, str] = {}
        # Primero los valores por defecto del HTML (incluye campos ocultos como el token CSRF)...
        for t in form.select("input[name], textarea[name], select[name]"):
            campos[str(t["name"])] = str(t.get("value", "") or t.get_text())
        # ...y luego, encima, lo que escribió el bot.
        campos.update(self._valores)
        # Sin atributo action, el formulario se envía a la misma URL (comportamiento HTML estándar).
        accion = urllib.parse.urljoin(self._url, str(form.get("action") or self._url))
        datos = urllib.parse.urlencode(campos).encode()
        # POST: datos en el cuerpo (urlencoded). GET: datos en la query string.
        if str(form.get("method", "get")).lower() == "post":
            self._pedir(accion, datos)
        else:
            self._pedir(accion + "?" + datos.decode())
