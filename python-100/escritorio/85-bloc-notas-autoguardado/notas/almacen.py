"""Almacenamiento de notas: un archivo JSON por nota, escrito de forma atómica.

Un archivo por nota hace que una corrupción afecte a una sola nota y que
el guardado sea barato. Las notas borradas van a ``papelera/`` y se pueden
restaurar.
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


def ahora_iso() -> str:
    """Marca de tiempo UTC ISO-8601 sin microsegundos (ordenable como texto). Se inyecta como
    ``reloj`` para tests deterministas.
    """
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Nota:
    """Una nota: id (uuid hex), texto libre y metadatos. Se guarda como un JSON por nota, así
    un archivo dañado solo afecta a una nota y no a todas.
    """
    id: str
    texto: str = ""
    creada: str = ""
    modificada: str = ""
    fijada: bool = False

    @property
    def titulo(self) -> str:
        """Primera línea no vacía, recortada; o "(vacía)"."""
        for linea in self.texto.splitlines():
            if linea.strip():
                t = linea.strip().lstrip("# ").strip()
                return t[:60] + ("…" if len(t) > 60 else "")
        return "(vacía)"


def escribir_atomico(ruta: Path, contenido: str) -> None:
    """Escribe en temporal + fsync + ``os.replace``: nunca deja un JSON a medias."""
    fd, tmp = tempfile.mkstemp(dir=ruta.parent, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(contenido)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, ruta)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class Almacen:
    """CRUD de notas en una carpeta. ``reloj`` es inyectable para tests."""

    def __init__(self, carpeta: Path, reloj=ahora_iso) -> None:
        """Carpeta de notas con subcarpeta ``papelera``. ``reloj`` permite fijar las fechas en
        los tests; ``corruptas`` acumula los archivos que no se pudieron leer para
        avisar en la GUI en vez de fallar.
        """
        self.carpeta = carpeta
        self.papelera = carpeta / "papelera"
        self.papelera.mkdir(parents=True, exist_ok=True)
        self.reloj = reloj
        self.corruptas: list[str] = []  # archivos ilegibles detectados al listar

    def _ruta(self, id_: str, papelera: bool = False) -> Path:
        """Ruta del JSON de una nota (en la carpeta o en la papelera)."""
        # El id es un uuid hex: se valida para impedir rutas tipo "../../etc".
        if not (len(id_) == 32 and all(c in "0123456789abcdef" for c in id_)):
            raise ValueError("id de nota inválido")
        return (self.papelera if papelera else self.carpeta) / f"{id_}.json"

    def crear(self, texto: str = "") -> Nota:
        """Nota nueva con creada = modificada = ahora; se persiste de inmediato."""
        t = self.reloj()
        nota = Nota(uuid.uuid4().hex, texto, t, t)
        self.guardar(nota, tocar=False)
        return nota

    def guardar(self, nota: Nota, tocar: bool = True) -> None:
        """Persiste con escritura atómica. ``tocar=False`` no actualiza 'modificada' (fijar una
        nota no debería subirla en el orden por fecha).
        """
        if tocar:
            nota.modificada = self.reloj()
        escribir_atomico(self._ruta(nota.id), json.dumps(asdict(nota), ensure_ascii=False, indent=1))

    def leer(self, id_: str) -> Nota:
        """Lee una nota ignorando campos desconocidos (compatibilidad con versiones futuras del
        formato).
        """
        datos = json.loads(self._ruta(id_).read_text("utf-8"))
        return Nota(**{k: datos[k] for k in Nota.__dataclass_fields__ if k in datos})

    def listar(self, filtro: str = "") -> list[Nota]:
        """Notas que contienen ``filtro`` (sin distinguir mayúsculas).

        Orden: fijadas primero, luego por fecha de modificación descendente.
        """
        notas, self.corruptas = [], []
        for archivo in self.carpeta.glob("*.json"):
            try:
                nota = self.leer(archivo.stem)
            except (ValueError, KeyError, TypeError, OSError):
                self.corruptas.append(archivo.name)
                continue
            if filtro.lower() in nota.texto.lower():
                notas.append(nota)
        notas.sort(key=lambda n: n.modificada, reverse=True)
        notas.sort(key=lambda n: not n.fijada)  # sort estable: conserva el orden por fecha
        return notas

    def borrar(self, id_: str) -> None:
        """Borrado suave: mueve el archivo a la papelera (``os.replace`` es atómico en el mismo
        disco).
        """
        os.replace(self._ruta(id_), self._ruta(id_, papelera=True))

    def restaurar(self, id_: str) -> Nota:
        """Devuelve una nota de la papelera a la carpeta principal y la retorna."""
        os.replace(self._ruta(id_, papelera=True), self._ruta(id_))
        return self.leer(id_)

    def en_papelera(self) -> list[str]:
        """Ids de las notas en la papelera, ordenados."""
        return sorted(p.stem for p in self.papelera.glob("*.json"))

    def vaciar_papelera(self) -> int:
        """Borra definitivamente lo que hay en la papelera; devuelve cuántas notas eliminó."""
        archivos = list(self.papelera.glob("*.json"))
        for a in archivos:
            a.unlink()
        return len(archivos)
