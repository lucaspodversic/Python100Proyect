"""Reglas de clasificación.

Una regla puede filtrar por extensión y/o por patrón de nombre (regex).
Se evalúan en orden: gana la primera que coincide. Así una regla
específica ("factura.*\\.pdf" → Facturas) puede ir antes que la genérica
(".pdf" → Documentos).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Regla:
    """Una regla: carpeta destino + filtro por extensiones y/o regex de nombre."""
    carpeta: str
    # Extensiones en minúsculas con punto (".pdf"); vacío = cualquier extensión.
    extensiones: frozenset[str] = field(default_factory=frozenset)
    patron: str | None = None  # regex sobre el nombre, sin distinguir mayúsculas

    def coincide(self, archivo: Path) -> bool:
        # Se compara en minúsculas: "FOTO.JPG" coincide con ".jpg".
        ext_ok = not self.extensiones or archivo.suffix.lower() in self.extensiones
        nom_ok = self.patron is None or re.search(self.patron, archivo.name, re.IGNORECASE) is not None
        # Ambos filtros deben cumplirse (el que no está definido se da por cumplido).
        return ext_ok and nom_ok

    @classmethod
    def desde_dict(cls, d: dict) -> "Regla":
        """Construye una regla desde JSON aceptando extensiones con o sin punto."""
        exts = frozenset(e.lower() if e.startswith(".") else "." + e.lower() for e in d.get("extensiones", []))
        return cls(d["carpeta"], exts, d.get("patron"))


def _r(carpeta: str, *exts: str) -> Regla:
    """Atajo para reglas sólo por extensión."""
    return Regla(carpeta, frozenset(exts))


# El orden importa: "Facturas" (PDF con nombre de factura) va antes que la regla genérica de PDF en Documentos.
REGLAS_POR_DEFECTO: tuple[Regla, ...] = (
    Regla("Facturas", frozenset({".pdf"}), r"factura|invoice|recibo"),
    _r("Imagenes", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".heic"),
    _r("Videos", ".mp4", ".mkv", ".mov", ".avi", ".webm"),
    _r("Musica", ".mp3", ".flac", ".wav", ".ogg", ".m4a"),
    _r("Documentos", ".pdf", ".doc", ".docx", ".odt", ".txt", ".md", ".rtf"),
    _r("Planillas", ".xls", ".xlsx", ".ods", ".csv"),
    _r("Presentaciones", ".ppt", ".pptx", ".odp"),
    _r("Comprimidos", ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"),
    _r("Instaladores", ".exe", ".msi", ".deb", ".rpm", ".dmg", ".appimage"),
    _r("Codigo", ".py", ".js", ".ts", ".java", ".c", ".cpp", ".go", ".rs", ".json", ".html", ".css"),
)

# Archivos que todavía se están descargando: nunca hay que moverlos
TEMPORALES = {".crdownload", ".part", ".partial", ".tmp", ".download", ".opdownload"}


def destino_para(archivo: Path, reglas: tuple[Regla, ...] = REGLAS_POR_DEFECTO,
                 por_defecto: str | None = "Otros") -> str | None:
    """Devuelve el nombre de carpeta destino o None si no hay que moverlo."""
    # Descargas en curso y archivos ocultos (configuración, nuestro propio registro) nunca se mueven.
    if archivo.suffix.lower() in TEMPORALES or archivo.name.startswith("."):
        return None
    # Gana la primera regla que coincide.
    for regla in reglas:
        if regla.coincide(archivo):
            return regla.carpeta
    # Sin coincidencias va a la carpeta por defecto (o None = dejarlo donde está).
    return por_defecto
