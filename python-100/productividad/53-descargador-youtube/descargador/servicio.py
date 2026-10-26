"""Servicio de descarga con backend intercambiable.

`Backend` es la interfaz. `BackendYtDlp` usa yt-dlp (import perezoso).
Elegimos yt-dlp porque pytube se rompe con frecuencia ante cambios de
YouTube, mientras que yt-dlp se actualiza seguido.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from .modelo import Formato, InfoVideo, elegir_formato, nombre_seguro, validar_url

Progreso = Callable[[int, int | None], None]  # (bytes bajados, total o None)


# Interfaz estructural: el backend real y el falso de los tests cumplen estos dos métodos.
class Backend(Protocol):
    def obtener_info(self, url: str) -> InfoVideo: ...
    def descargar(self, url: str, formatos: list[Formato], destino: Path, progreso: Progreso | None) -> Path: ...


class BackendYtDlp:
    """Adaptador sobre la API Python de yt-dlp."""

    def obtener_info(self, url: str) -> InfoVideo:
        import yt_dlp

        # Sólo metadatos: no se baja nada.
        with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True}) as ydl:
            d = ydl.extract_info(url, download=False)
        # Se traduce cada formato de yt-dlp; acodec/vcodec "none" indican que la pista no existe.
        fmts = tuple(
            Formato(f["format_id"], f.get("ext", ""), f.get("height"),
                    f.get("acodec") not in (None, "none"), f.get("vcodec") not in (None, "none"),
                    float(f.get("tbr") or 0), f.get("filesize"))
            for f in d.get("formats", []))
        # Si falta el título se usa el ID; duración desconocida → 0.
        return InfoVideo(d["id"], d.get("title", d["id"]), int(d.get("duration") or 0), fmts)

    def descargar(self, url: str, formatos: list[Formato], destino: Path, progreso: Progreso | None) -> Path:
        import yt_dlp

        # yt-dlp llama a este gancho periódicamente; se reenvía sólo el progreso de descarga.
        def gancho(e: dict) -> None:
            if progreso and e.get("status") == "downloading":
                progreso(int(e.get("downloaded_bytes") or 0), e.get("total_bytes"))

        # "137+251" pide a yt-dlp ambas pistas; outtmpl deja que yt-dlp ponga la extensión real; noplaylist evita bajar listas enteras.
        opciones = {"format": "+".join(f.id for f in formatos), "outtmpl": str(destino.with_suffix(".%(ext)s")),
                    "quiet": True, "progress_hooks": [gancho], "noplaylist": True}
        if len(formatos) == 2:
            opciones["merge_output_format"] = "mp4"  # combinar requiere ffmpeg instalado
        with yt_dlp.YoutubeDL(opciones) as ydl:
            ydl.download([url])
        return destino


@dataclass
class Descargador:
    """Orquesta validación, elección de formato, nombre de archivo y descarga."""
    backend: Backend

    def info(self, url: str) -> InfoVideo:
        validar_url(url)  # rechazamos URLs ajenas antes de llamar al backend
        return self.backend.obtener_info(url)

    def descargar(self, url: str, calidad: str, carpeta: Path, progreso: Progreso | None = None,
                  sobrescribir: bool = False) -> Path:
        info = self.info(url)
        # 1 formato (progresivo o audio) o 2 (video + audio).
        elegidos = elegir_formato(info.formatos, calidad)
        # Si se combinan dos pistas el resultado es mp4 (merge_output_format).
        ext = "mp4" if len(elegidos) == 2 else elegidos[0].extension
        destino = Path(carpeta) / nombre_seguro(info.titulo, ext)
        # Caso borde: no se pisa una descarga previa sin pedirlo.
        if destino.exists() and not sobrescribir:
            raise FileExistsError(f"Ya existe {destino}")
        destino.parent.mkdir(parents=True, exist_ok=True)
        return self.backend.descargar(url, elegidos, destino, progreso)
