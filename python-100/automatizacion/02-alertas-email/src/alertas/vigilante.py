"""Detección de cambios en carpetas por *polling* de instantáneas.

Se eligió polling (en vez de inotify/watchdog) porque funciona igual en
carpetas de red (SMB/NFS) donde los eventos del SO no son confiables, y no
requiere dependencias externas.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from .notificador import Notificador

# Una instantánea mapea ruta relativa -> huella (tamaño, mtime, sha256).
Instantanea = dict[str, dict[str, object]]


@dataclass(frozen=True)
class Cambio:
    """Cambio detectado entre dos instantáneas."""

    tipo: str  # "creado" | "modificado" | "eliminado"
    ruta: str


def _sha256(ruta: Path, bloque: int = 65536) -> str:
    """Hash del contenido leyendo por bloques (no carga archivos enteros en RAM)."""
    # Bloques de 64 KiB: buen equilibrio entre cantidad de llamadas al SO y memoria usada.
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        # ``iter(callable, centinela)`` llama a f.read hasta que devuelva b"" (fin de archivo).
        for trozo in iter(lambda: f.read(bloque), b""):
            h.update(trozo)
    return h.hexdigest()


def tomar_instantanea(raiz: Path, patrones: Iterable[str] = ("*",)) -> Instantanea:
    """Recorre ``raiz`` y registra la huella de cada archivo que matchee algún patrón.

    Se usa el hash además de mtime porque algunas herramientas reescriben
    archivos sin cambiar contenido (falso positivo) o preservan mtime al copiar
    (falso negativo).
    """
    patrones = list(patrones)
    resultado: Instantanea = {}
    # ``sorted`` hace el recorrido determinista (el orden de rglob depende del sistema de archivos).
    for archivo in sorted(raiz.rglob("*")):
        if not archivo.is_file():
            continue
        # Claves relativas y con "/" para que el estado JSON sea portable entre Windows y Linux.
        rel = archivo.relative_to(raiz).as_posix()
        # El patrón se prueba contra la ruta relativa ("informes/*.xlsx") Y contra el nombre ("*.xlsx"),
        # así un patrón simple también encuentra archivos en subcarpetas.
        if not any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(archivo.name, p) for p in patrones):
            continue
        st = archivo.stat()
        resultado[rel] = {"tamano": st.st_size, "mtime": st.st_mtime, "sha256": _sha256(archivo)}
    return resultado


def comparar(anterior: Instantanea, actual: Instantanea) -> list[Cambio]:
    """Diferencia dos instantáneas. Sólo el hash define si hubo modificación."""
    cambios: list[Cambio] = []
    # Diferencia de conjuntos de claves: presente ahora y no antes → creado.
    for ruta in sorted(actual.keys() - anterior.keys()):
        cambios.append(Cambio("creado", ruta))
    # Presente antes y no ahora → eliminado.
    for ruta in sorted(anterior.keys() - actual.keys()):
        cambios.append(Cambio("eliminado", ruta))
    # En ambas: sólo cuenta como modificado si cambió el hash; un cambio de mtime solo
    # (p. ej. ``touch`` o reescribir el mismo contenido) NO genera alerta.
    for ruta in sorted(actual.keys() & anterior.keys()):
        if actual[ruta]["sha256"] != anterior[ruta]["sha256"]:
            cambios.append(Cambio("modificado", ruta))
    return cambios


def formatear_mensaje(raiz: Path, cambios: list[Cambio]) -> tuple[str, str]:
    """Arma asunto y cuerpo del email a partir de la lista de cambios."""
    asunto = f"[Alerta] {len(cambios)} cambio(s) en {raiz.name}"
    lineas = [f"Se detectaron cambios en {raiz}:", ""]
    # Símbolos estilo diff para que el email se lea de un vistazo; ``:<10`` alinea la columna del tipo.
    iconos = {"creado": "+", "modificado": "~", "eliminado": "-"}
    lineas += [f"  {iconos[c.tipo]} {c.tipo:<10} {c.ruta}" for c in cambios]
    return asunto, "\n".join(lineas)


@dataclass
class Vigilante:
    """Orquesta: toma instantáneas, compara, notifica y persiste el estado.

    ``estado`` es un JSON donde se guarda la última instantánea para que,
    al reiniciar el proceso, no se reenvíen alertas de cambios ya avisados.
    """

    raiz: Path
    notificador: Notificador
    destinatarios: list[str]
    patrones: list[str] = field(default_factory=lambda: ["*"])
    estado: Path | None = None
    # None = todavía no hay línea base (primera pasada).
    _anterior: Instantanea | None = None

    def __post_init__(self) -> None:
        # Si hay un estado previo en disco, lo cargamos como punto de partida.
        if self.estado is not None and self.estado.exists():
            self._anterior = json.loads(self.estado.read_text(encoding="utf-8"))

    def revisar(self) -> list[Cambio]:
        """Hace una pasada: devuelve los cambios y notifica si hay alguno.

        La primera pasada sin estado previo sólo establece la línea base
        (no tendría sentido avisar que "se crearon" todos los archivos).
        """
        actual = tomar_instantanea(self.raiz, self.patrones)
        cambios: list[Cambio] = []
        if self._anterior is not None:
            cambios = comparar(self._anterior, actual)
            if cambios:
                asunto, cuerpo = formatear_mensaje(self.raiz, cambios)
                self.notificador.enviar(asunto, cuerpo, self.destinatarios)
        # La instantánea actual pasa a ser la referencia de la próxima pasada (haya o no cambios).
        self._anterior = actual
        # Se persiste DESPUÉS de notificar: si el envío falla con excepción, el estado no avanza y
        # el cambio se vuelve a avisar en la próxima pasada (preferimos duplicar a perder una alerta).
        if self.estado is not None:
            self.estado.write_text(json.dumps(actual), encoding="utf-8")
        return cambios

    def vigilar(
        self,
        intervalo: float = 60.0,
        iteraciones: int | None = None,
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        """Bucle de vigilancia. ``dormir`` es inyectable para testear sin esperar."""
        n = 0
        # No dormimos después de la última iteración: con iteraciones=3 hay exactamente 2 esperas.
        while iteraciones is None or n < iteraciones:
            self.revisar()
            n += 1
            if iteraciones is None or n < iteraciones:
                dormir(intervalo)
