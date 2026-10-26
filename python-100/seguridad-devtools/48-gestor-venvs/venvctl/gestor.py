"""Gestor de entornos virtuales guardados en una carpeta central.

Por defecto los entornos viven en ~/.venvctl/<nombre> (configurable con
la variable VENVCTL_HOME). Las acciones que lanzan procesos (pip) pasan
por un "ejecutor" inyectable para poder testear sin instalar nada.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import venv
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

# Empieza con letra o número (nada de ".oculto" ni "-opcion"), sin "/" ni "\", 64 caracteres como máximo.
NOMBRE_VALIDO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
# Recibe el comando como lista de argumentos y devuelve su stdout.
Ejecutor = Callable[[Sequence[str]], str]


class ErrorGestor(Exception):
    """Error de uso: nombre inválido, entorno inexistente o duplicado."""


def ejecutor_real(cmd: Sequence[str]) -> str:
    """Ejecuta un comando sin shell (evita inyección) y devuelve stdout."""
    # check=True lanza CalledProcessError si pip falla; capture_output evita mezclar su salida con la nuestra.
    return subprocess.run(list(cmd), check=True, capture_output=True, text=True).stdout


def creador_real(ruta: Path, con_pip: bool) -> None:
    """Crea el entorno con el módulo estándar `venv`."""
    # Symlinks al intérprete en Unix (ahorra espacio); en Windows se copian porque los symlinks requieren permisos.
    venv.EnvBuilder(with_pip=con_pip, symlinks=os.name != "nt").create(ruta)


@dataclass(frozen=True)
class InfoEntorno:
    """Datos de un entorno: nombre, ruta, versión de Python y tamaño en disco."""
    nombre: str
    ruta: Path
    version_python: str
    tamano_bytes: int


def _carpeta_bin(ruta: Path) -> Path:
    """Scripts/ en Windows, bin/ en Unix."""
    return ruta / ("Scripts" if os.name == "nt" else "bin")


class Gestor:
    """Operaciones sobre los entornos de la carpeta central."""

    def __init__(self, base: Path | None = None, ejecutor: Ejecutor = ejecutor_real,
                 creador: Callable[[Path, bool], None] = creador_real) -> None:
        # Precedencia de la carpeta: argumento > variable VENVCTL_HOME > ~/.venvctl. resolve() la vuelve absoluta.
        self.base = Path(base or os.environ.get("VENVCTL_HOME") or Path.home() / ".venvctl").resolve()
        self.ejecutor = ejecutor
        self.creador = creador

    def _ruta(self, nombre: str) -> Path:
        """Valida el nombre y devuelve la ruta, impidiendo salir de la base."""
        if not NOMBRE_VALIDO.match(nombre):
            raise ErrorGestor(f"Nombre inválido: {nombre!r} (usar letras, números, . _ -)")
        # resolve() sigue symlinks y "..": si el resultado no es hijo directo de la base, se rechaza.
        ruta = (self.base / nombre).resolve()
        if ruta.parent != self.base:  # defensa extra ante path traversal
            raise ErrorGestor("Ruta fuera de la carpeta de entornos")
        return ruta

    def crear(self, nombre: str, paquetes: Sequence[str] = (), con_pip: bool = True) -> Path:
        """Crea un entorno nuevo y, si se pasan paquetes, los instala con pip."""
        ruta = self._ruta(nombre)
        if ruta.exists():
            raise ErrorGestor(f"El entorno {nombre} ya existe")
        # La carpeta central se crea recién al primer uso.
        self.base.mkdir(parents=True, exist_ok=True)
        # Si hay paquetes para instalar, pip es imprescindible aunque se haya pedido sin pip.
        self.creador(ruta, con_pip or bool(paquetes))
        if paquetes:
            self.instalar(nombre, paquetes)
        return ruta

    def listar(self) -> list[str]:
        """Nombres de los entornos de la base, en orden alfabético."""
        if not self.base.exists():
            return []
        # Sólo cuentan las carpetas con pyvenv.cfg (el marcador que crea `venv`).
        return sorted(p.name for p in self.base.iterdir() if (p / "pyvenv.cfg").exists())

    def eliminar(self, nombre: str) -> None:
        """Borra un entorno completo (sólo si realmente es un venv)."""
        ruta = self._ruta(nombre)
        if not (ruta / "pyvenv.cfg").exists():
            # Sólo borramos carpetas que realmente son venvs
            raise ErrorGestor(f"{nombre} no es un entorno gestionado")
        shutil.rmtree(ruta)

    def python(self, nombre: str) -> Path:
        """Ruta al intérprete del entorno (valida que exista)."""
        ruta = self._ruta(nombre)
        if not (ruta / "pyvenv.cfg").exists():
            raise ErrorGestor(f"No existe el entorno {nombre}")
        return _carpeta_bin(ruta) / ("python.exe" if os.name == "nt" else "python")

    def instalar(self, nombre: str, paquetes: Sequence[str]) -> str:
        """Instala paquetes con el pip del propio entorno (no el global)."""
        # `python -m pip` garantiza usar el pip de ese intérprete; los paquetes van como argumentos separados (sin shell).
        return self.ejecutor([str(self.python(nombre)), "-m", "pip", "install", *paquetes])

    def congelar(self, nombre: str) -> str:
        """Equivale a `pip freeze` dentro del entorno."""
        return self.ejecutor([str(self.python(nombre)), "-m", "pip", "freeze"])

    def comando_activar(self, nombre: str, shell: str = "bash") -> str:
        """Un proceso hijo no puede activar la shell del padre: devolvemos el
        comando para que el usuario lo evalúe (p. ej. `eval "$(venvctl activar x)"`)."""
        # Se devuelve el comando de activación según la shell; KeyError si la shell no está en el dict
        # (la CLI lo impide con choices).
        b = _carpeta_bin(self._ruta(nombre))
        self.python(nombre)  # valida existencia
        return {"bash": f"source {b / 'activate'}", "zsh": f"source {b / 'activate'}",
                "fish": f"source {b / 'activate.fish'}", "powershell": f"& '{b / 'Activate.ps1'}'",
                "cmd": str(b / "activate.bat")}[shell]

    def info(self, nombre: str) -> InfoEntorno:
        """Lee la versión de Python de pyvenv.cfg y calcula el tamaño en disco."""
        ruta = self._ruta(nombre)
        cfg = ruta / "pyvenv.cfg"
        if not cfg.exists():
            raise ErrorGestor(f"No existe el entorno {nombre}")
        version = ""
        # pyvenv.cfg tiene líneas "clave = valor"; según la versión de Python la clave es version o version_info.
        for linea in cfg.read_text().splitlines():
            clave, _, valor = linea.partition("=")
            if clave.strip() in {"version", "version_info"}:
                version = valor.strip()
        # Se ignoran symlinks para no contar el intérprete del sistema al que apuntan.
        tam = sum(f.stat().st_size for f in ruta.rglob("*") if f.is_file() and not f.is_symlink())
        # Si el cfg no trae versión se usa la del intérprete actual como aproximación.
        return InfoEntorno(nombre, ruta, version or sys.version.split()[0], tam)
