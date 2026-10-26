"""Orquestador del bot: recorre, evalúa y postula con límites de seguridad."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urljoin, urlsplit

from .navegador import Navegador
from .paginas import PaginaListado, PaginaOferta
from .perfil import Decision, Oferta, Perfil, evaluar

# Lista blanca de loopback (IPv4, nombre y IPv6). Es una lista blanca y no negra a propósito:
# cualquier host que no esté acá queda prohibido, incluidos dominios que no anticipamos.
HOSTS_LOCALES = {"127.0.0.1", "localhost", "::1"}


def validar_url_local(url: str) -> None:
    """Impide apuntar el bot a sitios reales: sólo se permite loopback.

    Automatizar portales reales (LinkedIn, etc.) viola sus términos de uso y
    puede provocar el bloqueo de la cuenta. Este proyecto es demostrativo.
    """
    # ``hostname`` ya viene en minúsculas y sin puerto ni corchetes IPv6 ("[::1]:80" → "::1").
    host = urlsplit(url).hostname or ""
    if host not in HOSTS_LOCALES:
        raise ValueError(f"Por seguridad sólo se permite el sitio mock local, no {host!r}")


@dataclass
class Resultado:
    """Registro de lo que hizo el bot con cada oferta."""

    oferta: Oferta
    decision: Decision
    postulado: bool


class Registro:
    """Historial en SQLite para no postular dos veces a la misma oferta."""

    def __init__(self, ruta: str = ":memory:") -> None:
        # ":memory:" por defecto: cada instancia tiene su propia base efímera (ideal para tests);
        # con una ruta de archivo el historial sobrevive entre corridas.
        self.db = sqlite3.connect(ruta)
        self.db.execute("CREATE TABLE IF NOT EXISTS postulaciones (id TEXT PRIMARY KEY, titulo TEXT, fecha REAL)")

    def ya_postulado(self, oferta_id: str) -> bool:
        # Consulta parametrizada (?) para no concatenar texto en el SQL (evita inyección).
        return self.db.execute("SELECT 1 FROM postulaciones WHERE id=?", (oferta_id,)).fetchone() is not None

    def guardar(self, oferta: Oferta) -> None:
        # OR IGNORE: si por algún motivo se reintenta la misma oferta, la PRIMARY KEY no lanza error.
        self.db.execute("INSERT OR IGNORE INTO postulaciones VALUES (?,?,?)", (oferta.id, oferta.titulo, time.time()))
        self.db.commit()


@dataclass
class BotPostulaciones:
    """Bot con *dry-run*, máximo de postulaciones y pausa entre acciones."""

    nav: Navegador
    perfil: Perfil
    url_inicio: str
    dry_run: bool = True  # por defecto NO postula: hay que pedirlo explícitamente
    max_postulaciones: int = 5
    pausa: float = 3.0  # segundos entre acciones (rate limiting)
    max_paginas: int = 10
    # default_factory: cada bot nuevo recibe un Registro propio (no compartido entre instancias).
    registro: Registro = field(default_factory=Registro)
    dormir: Callable[[float], None] = time.sleep

    def __post_init__(self) -> None:
        # La validación ocurre al construir el bot: es imposible crear uno que apunte a un sitio real.
        validar_url_local(self.url_inicio)

    def ejecutar(self) -> list[Resultado]:
        resultados: list[Resultado] = []
        postuladas = 0
        self.nav.ir(self.url_inicio)
        # Cota de páginas: aunque el sitio tuviera paginación infinita, el bot termina.
        for _ in range(self.max_paginas):
            listado = PaginaListado(self.nav)
            # Guardamos la URL del listado porque al entrar en cada detalle el navegador "se va" de la página.
            url_listado = self.nav.url_actual
            for oferta, enlace in listado.ofertas():
                # Límite duro de postulaciones por corrida: corta inmediatamente (incluso a mitad de página).
                if postuladas >= self.max_postulaciones:
                    return resultados
                # Idempotencia: las ofertas ya registradas se saltan sin siquiera abrir el detalle.
                if self.registro.ya_postulado(oferta.id):
                    continue
                # Pausa antes de cada navegación: imita el ritmo humano y no satura el servidor.
                self.dormir(self.pausa)
                self.nav.ir(urljoin(url_listado, enlace))
                detalle = PaginaOferta(self.nav)
                # El listado sólo trae un resumen; las palabras clave se buscan en la descripción completa.
                oferta.descripcion = detalle.descripcion()
                decision = evaluar(oferta, self.perfil)
                postulado = False
                # Tres condiciones para postular de verdad: las reglas lo aprueban, NO es dry-run y el sitio
                # no indica que ya nos postulamos (doble control: registro local + estado del sitio).
                if decision.aplicar and not self.dry_run and not detalle.ya_postulado():
                    self.dormir(self.pausa)
                    postulado = detalle.abrir_formulario().completar_y_enviar(self.perfil)
                    # Sólo se registra y cuenta si el sitio confirmó el envío (si el formulario falló, se reintentará).
                    if postulado:
                        self.registro.guardar(oferta)
                        postuladas += 1
                resultados.append(Resultado(oferta, decision, postulado))
            # Volvemos al listado para seguir la paginación.
            self.nav.ir(url_listado)
            # Se recrea el Page Object tras volver, porque el HTML cargado es nuevo.
            listado = PaginaListado(self.nav)
            if not listado.hay_siguiente():
                break
            self.dormir(self.pausa)
            listado.ir_siguiente()
        return resultados
