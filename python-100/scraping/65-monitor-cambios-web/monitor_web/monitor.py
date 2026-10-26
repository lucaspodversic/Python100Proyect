"""Lógica del monitor.

Estado persistido por objetivo: huella, texto, ETag y Last-Modified.
Se usan **pedidos condicionales** (If-None-Match / If-Modified-Since):
si el servidor responde 304, no se descarga nada nuevo → menos carga.
"""
from __future__ import annotations

import difflib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .cliente import ClienteEducado
from .extraccion import extraer_texto, huella


@dataclass(frozen=True)
class Objetivo:
    """Qué vigilar: nombre legible, URL, región opcional (selector) y regex de ruido a ignorar."""

    nombre: str
    url: str
    selector: str | None = None
    ignorar: tuple[str, ...] = ()   # tupla (inmutable) para que el dataclass frozen sea hasheable

    @classmethod
    def desde_dict(cls, d: dict) -> "Objetivo":
        """Construye desde una entrada del config JSON; sólo 'nombre' y 'url' son obligatorios."""
        return cls(d["nombre"], d["url"], d.get("selector"), tuple(d.get("ignorar", ())))


@dataclass(frozen=True)
class Cambio:
    """Un cambio detectado, listo para notificar."""

    nombre: str
    url: str
    diff: str        # diff unificado (formato de `git diff`)
    agregadas: int   # líneas que aparecen sólo en la versión nueva
    quitadas: int    # líneas que desaparecieron
    momento: str     # ISO 8601 en UTC


def hacer_diff(antes: str, despues: str, nombre: str) -> tuple[str, int, int]:
    """Diff unificado con 1 línea de contexto + conteo de líneas agregadas/quitadas."""
    lineas = list(difflib.unified_diff(antes.splitlines(), despues.splitlines(),
                                       f"{nombre} (antes)", f"{nombre} (ahora)", lineterm="", n=1))
    # Las cabeceras '+++'/'---' del diff no son cambios: se excluyen del conteo.
    mas = sum(1 for l in lineas if l.startswith("+") and not l.startswith("+++"))
    menos = sum(1 for l in lineas if l.startswith("-") and not l.startswith("---"))
    return "\n".join(lineas), mas, menos


@dataclass
class Monitor:
    """Revisa una lista de objetivos y avisa a los notificadores cuando algo cambia."""

    objetivos: list[Objetivo]
    estado_ruta: Path                                             # JSON con lo visto la última vez
    cliente: ClienteEducado = field(default_factory=ClienteEducado)
    notificadores: list = field(default_factory=list)
    ahora: Callable[[], datetime] = lambda: datetime.now(timezone.utc)  # reloj inyectable (tests deterministas)

    def _cargar(self) -> dict:
        """Estado previo; si el archivo no existe es la primera ejecución (estado vacío)."""
        p = Path(self.estado_ruta)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def _guardar(self, estado: dict) -> None:
        # ensure_ascii=False: el JSON queda legible con tildes y ñ.
        Path(self.estado_ruta).write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")

    def revisar(self) -> list[Cambio]:
        """Una pasada por todos los objetivos. La primera vez sólo guarda la línea base."""
        estado = self._cargar()
        cambios: list[Cambio] = []
        for o in self.objetivos:
            # El estado se indexa por URL: renombrar un objetivo no pierde su historial.
            previo = estado.get(o.url, {})
            # Pedido condicional: si el servidor soporta ETag/Last-Modified y nada cambió,
            # responde 304 sin cuerpo (ahorra ancho de banda a ambos lados).
            cab = {}
            if previo.get("etag"):
                cab["If-None-Match"] = previo["etag"]
            if previo.get("modificado"):
                cab["If-Modified-Since"] = previo["modificado"]
            r = self.cliente.get(o.url, cab)
            if r.estado == 304:
                continue  # sin cambios según el servidor
            texto = extraer_texto(r.texto(), o.selector, o.ignorar)
            h = huella(texto)
            # Sólo hay "cambio" si ya existía una línea base y la huella es distinta.
            # Caso borde: primera ejecución (previo vacío) → no se notifica nada.
            if previo and previo.get("huella") != h:
                diff, mas, menos = hacer_diff(previo.get("texto", ""), texto, o.nombre)
                c = Cambio(o.nombre, o.url, diff, mas, menos, self.ahora().isoformat())
                cambios.append(c)
                for n in self.notificadores:
                    n.notificar(c)
            # Se guarda el texto completo (no sólo la huella) para poder generar el diff la próxima vez.
            estado[o.url] = {"huella": h, "texto": texto, "etag": r.cabeceras.get("etag"),
                             "modificado": r.cabeceras.get("last-modified"), "revisado": self.ahora().isoformat()}
        # Se persiste al final de la pasada (una escritura por revisión, no por objetivo).
        self._guardar(estado)
        return cambios

    def vigilar(self, intervalo: float, iteraciones: int | None = None,
                dormir: Callable[[float], None] = time.sleep) -> int:
        """Repite `revisar` cada `intervalo` segundos. iteraciones=None → infinito (Ctrl+C para salir).

        Devuelve la cantidad total de cambios detectados.
        """
        total, i = 0, 0
        while iteraciones is None or i < iteraciones:
            total += len(self.revisar())
            i += 1
            # No se duerme después de la última iteración: el programa termina enseguida.
            if iteraciones is None or i < iteraciones:
                dormir(intervalo)
        return total
