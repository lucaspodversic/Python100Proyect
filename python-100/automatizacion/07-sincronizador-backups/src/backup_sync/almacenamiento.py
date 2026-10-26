"""Interfaz de almacenamiento remoto + implementaciones locales.

Un "almacenamiento" es un key-value de bytes: claves con ``/`` como
separador (estilo S3). Todo backend (S3, Drive, carpeta, memoria) cumple
el mismo ``Protocol``, así el sincronizador no sabe dónde guarda.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


# Cinco operaciones bastan para un backup incremental con versiones y restauración.
# Mantener la interfaz chica hace trivial agregar backends (SFTP, Azure Blob, etc.).
class Almacenamiento(Protocol):
    def listar(self, prefijo: str = "") -> list[str]: ...

    def subir(self, clave: str, datos: bytes) -> None: ...

    def descargar(self, clave: str) -> bytes: ...

    def borrar(self, clave: str) -> None: ...

    def existe(self, clave: str) -> bool: ...


@dataclass
class MemoriaAlmacenamiento:
    """Backend en memoria: ideal para tests."""

    objetos: dict[str, bytes] = field(default_factory=dict)
    subidas: int = 0  # contador para verificar que la sync es incremental

    def listar(self, prefijo: str = "") -> list[str]:
        # Listado ordenado en todos los backends: resultados deterministas y comparables en tests.
        return sorted(k for k in self.objetos if k.startswith(prefijo))

    def subir(self, clave: str, datos: bytes) -> None:
        self.objetos[clave] = datos
        self.subidas += 1

    def descargar(self, clave: str) -> bytes:
        return self.objetos[clave]

    def borrar(self, clave: str) -> None:
        # Borrar algo inexistente no es error (idempotente, igual que S3).
        self.objetos.pop(clave, None)

    def existe(self, clave: str) -> bool:
        return clave in self.objetos


@dataclass
class CarpetaAlmacenamiento:
    """Backend sobre una carpeta (disco externo, NAS montado, carpeta de Dropbox...)."""

    raiz: Path

    def _ruta(self, clave: str) -> Path:
        # ``resolve()`` colapsa ".." y symlinks ANTES de validar; si no, "a/../../x" pasaría el chequeo.
        ruta = (self.raiz / clave).resolve()
        # Evita path traversal ("../../etc") con claves maliciosas.
        if not ruta.is_relative_to(self.raiz.resolve()):
            raise ValueError(f"Clave fuera de la raíz: {clave}")
        return ruta

    def listar(self, prefijo: str = "") -> list[str]:
        if not self.raiz.exists():
            return []
        # Claves con "/" aunque estemos en Windows: el manifiesto es portable entre sistemas.
        claves = (p.relative_to(self.raiz).as_posix() for p in self.raiz.rglob("*") if p.is_file())
        return sorted(c for c in claves if c.startswith(prefijo))

    def subir(self, clave: str, datos: bytes) -> None:
        ruta = self._ruta(clave)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        # Se escribe primero a "archivo.ext.tmp" y luego se renombra: ``replace`` es atómico en el
        # mismo sistema de archivos, así un corte de luz nunca deja un archivo truncado.
        tmp = ruta.with_suffix(ruta.suffix + ".tmp")
        tmp.write_bytes(datos)
        tmp.replace(ruta)  # escritura atómica: nunca queda un backup a medias

    def descargar(self, clave: str) -> bytes:
        return self._ruta(clave).read_bytes()

    def borrar(self, clave: str) -> None:
        # missing_ok: borrar un archivo que ya no existe es una operación válida (idempotente).
        self._ruta(clave).unlink(missing_ok=True)

    def existe(self, clave: str) -> bool:
        return self._ruta(clave).is_file()
