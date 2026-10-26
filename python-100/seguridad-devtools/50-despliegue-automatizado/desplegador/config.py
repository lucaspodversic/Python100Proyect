"""Configuración del despliegue (leída de un archivo TOML)."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ConfigDespliegue:
    """Parámetros del destino. Ejemplo en `deploy.example.toml`."""

    host: str
    usuario: str
    repo: str                      # URL git que el servidor puede clonar
    ruta_base: str                 # p. ej. /srv/miapp
    rama: str = "main"
    puerto: int = 22
    clave_ssh: str | None = None   # ruta a la clave privada (nunca la clave en sí)
    comandos_build: list[str] = field(default_factory=list)   # se ejecutan dentro del release
    comando_reinicio: str = ""     # p. ej. "sudo systemctl restart miapp"
    comando_salud: str = ""        # p. ej. "curl -fsS http://127.0.0.1:8000/health"
    releases_a_conservar: int = 5

    @classmethod
    def desde_toml(cls, ruta: Path) -> "ConfigDespliegue":
        """Lee la tabla [deploy] del TOML; claves desconocidas o faltantes fallan con TypeError."""
        with open(ruta, "rb") as f:
            # KeyError si el archivo no tiene la sección [deploy].
            datos = tomllib.load(f)["deploy"]
        return cls(**datos)
