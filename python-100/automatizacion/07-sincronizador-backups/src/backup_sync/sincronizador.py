"""Lógica de sincronización incremental.

Se guarda en el destino un **manifiesto** (``.backup_manifiesto.json``) con
el SHA-256 de cada archivo respaldado. Comparando contra el manifiesto se
sabe qué subir sin descargar nada: sólo viajan los archivos nuevos o
modificados (eficiente en ancho de banda y costo).
"""

from __future__ import annotations

import datetime as dt
import fnmatch
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from .almacenamiento import Almacenamiento

MANIFIESTO = ".backup_manifiesto.json"
# Las versiones viven en el mismo destino bajo un prefijo reservado: _versiones/<sello>/<ruta>.
VERSIONES = "_versiones"


def sha256(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


@dataclass
class Plan:
    """Qué hará la sincronización (se puede mostrar en dry-run)."""

    subir: list[str] = field(default_factory=list)
    actualizar: list[str] = field(default_factory=list)
    borrar: list[str] = field(default_factory=list)
    sin_cambios: int = 0

    @property
    # "sin_cambios" no cuenta: un plan sin subidas, actualizaciones ni borrados está vacío.
    def vacio(self) -> bool:
        return not (self.subir or self.actualizar or self.borrar)


@dataclass
class Sincronizador:
    """Respalda ``origen`` en ``destino``.

    :param espejo: si es ``True`` borra del destino lo que ya no existe localmente.
    :param versionar: guarda la versión anterior en ``_versiones/<fecha>/`` antes de pisarla.
    :param excluir: patrones glob a ignorar (``*.tmp``, ``node_modules/*``...).
    """

    origen: Path
    destino: Almacenamiento
    espejo: bool = False
    versionar: bool = True
    # Exclusiones por defecto: temporales, archivos de bloqueo de Office (~$) y basura del SO.
    excluir: list[str] = field(default_factory=lambda: ["*.tmp", "~$*", ".DS_Store", "Thumbs.db"])

    def _locales(self) -> dict[str, Path]:
        archivos: dict[str, Path] = {}
        for p in sorted(self.origen.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(self.origen).as_posix()
            # Patrón contra ruta relativa ("sub/*") o contra el nombre ("*.tmp", en cualquier nivel).
            if any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(p.name, pat) for pat in self.excluir):
                continue
            archivos[rel] = p
        return archivos

    def _manifiesto(self) -> dict[str, str]:
        # Primera sincronización: no hay manifiesto → todo cuenta como nuevo.
        if self.destino.existe(MANIFIESTO):
            return json.loads(self.destino.descargar(MANIFIESTO))
        return {}

    def planificar(self) -> tuple[Plan, dict[str, str], dict[str, Path]]:
        """Compara hashes locales contra el manifiesto remoto."""
        locales = self._locales()
        remoto = self._manifiesto()
        # Se compara por hash y no por mtime: copiar o restaurar archivos cambia el mtime sin cambiar
        # contenido, y algunos programas preservan mtime al modificar.
        hashes = {rel: sha256(p.read_bytes()) for rel, p in locales.items()}
        plan = Plan()
        for rel, h in hashes.items():
            if rel not in remoto:
                plan.subir.append(rel)
            elif remoto[rel] != h:
                plan.actualizar.append(rel)
            else:
                plan.sin_cambios += 1
        # Sólo en modo espejo se borra lo que está en el manifiesto pero ya no existe localmente.
        if self.espejo:
            plan.borrar = sorted(set(remoto) - set(hashes))
        return plan, hashes, locales

    def sincronizar(self, dry_run: bool = False, ahora: dt.datetime | None = None) -> Plan:
        plan, hashes, locales = self.planificar()
        # Dry-run devuelve el plan sin tocar el destino; con plan vacío no se reescribe el manifiesto.
        if dry_run or plan.vacio:
            return plan
        # Sello ISO compacto (20240501T120000): ordena cronológicamente y es válido como nombre de carpeta.
        # ``ahora`` inyectable para tests deterministas.
        sello = (ahora or dt.datetime.now()).strftime("%Y%m%dT%H%M%S")
        manifiesto = self._manifiesto()
        # Versionado ANTES de pisar o borrar: la copia anterior se guarda en _versiones/<sello>/.
        for rel in plan.actualizar + plan.borrar:
            if self.versionar and self.destino.existe(rel):
                self.destino.subir(f"{VERSIONES}/{sello}/{rel}", self.destino.descargar(rel))
        # Se actualiza el manifiesto archivo por archivo, pero se persiste una sola vez al final.
        for rel in plan.subir + plan.actualizar:
            self.destino.subir(rel, locales[rel].read_bytes())
            manifiesto[rel] = hashes[rel]
        for rel in plan.borrar:
            self.destino.borrar(rel)
            manifiesto.pop(rel, None)
        # El manifiesto se escribe al final: si algo falla a mitad, la próxima
        # corrida vuelve a subir lo pendiente (operación reintentable).
        self.destino.subir(MANIFIESTO, json.dumps(manifiesto, indent=1, sort_keys=True).encode())
        return plan

    def restaurar(self, carpeta: Path, version: str | None = None) -> int:
        """Descarga el backup (o una versión ``_versiones/<sello>``) a ``carpeta``."""
        # Restaurar una versión: claves bajo _versiones/<sello>/, quitando ese prefijo para la ruta local.
        # Sólo contiene los archivos que cambiaron en esa corrida, no un snapshot completo.
        if version:
            pref = f"{VERSIONES}/{version}/"
            claves = {c[len(pref):]: c for c in self.destino.listar(pref)}
        else:
            # Restaurar lo actual: el manifiesto es la fuente de verdad (ignora _versiones y el propio manifiesto).
            claves = {c: c for c in self._manifiesto()}
        for rel, clave in claves.items():
            ruta = carpeta / rel
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_bytes(self.destino.descargar(clave))
        return len(claves)
