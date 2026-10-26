"""Sincronizador de backups incremental con backends intercambiables."""

# Backends locales (memoria, carpeta) y de nube (S3, Drive) comparten la misma interfaz;
# el Sincronizador sólo depende del Protocol Almacenamiento.
from .almacenamiento import Almacenamiento, CarpetaAlmacenamiento, MemoriaAlmacenamiento
from .nube import DriveAlmacenamiento, S3Almacenamiento
from .sincronizador import Plan, Sincronizador

__all__ = ["Almacenamiento", "CarpetaAlmacenamiento", "MemoriaAlmacenamiento",
           "S3Almacenamiento", "DriveAlmacenamiento", "Plan", "Sincronizador"]
