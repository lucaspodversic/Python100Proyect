"""CLI: descargador URL [-c 720p|mejor|audio] [-o carpeta] [--info]."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .servicio import Backend, BackendYtDlp, Descargador

# Recordatorio legal que se muestra antes de cada descarga y en --help.
AVISO = "Descargá sólo contenido propio o con permiso del titular (Términos de Servicio de YouTube)."


def barra(bajado: int, total: int | None) -> None:
    """Imprime una barra de progreso simple en la misma línea."""
    if total:
        # 25 casilleros: cada "#" representa un 4 %.
        pct = bajado * 100 // total
        sys.stderr.write(f"\r[{'#' * (pct // 4):<25}] {pct:3d}%")
    else:
        # Sin total conocido sólo se muestran los MB bajados.
        sys.stderr.write(f"\r{bajado / 1e6:.1f} MB")


# `backend` inyectable: los tests pasan uno falso y nunca se contacta a YouTube.
def ejecutar(argv: Sequence[str] | None = None, backend: Backend | None = None) -> int:
    p = argparse.ArgumentParser(prog="descargador", description=AVISO)
    p.add_argument("url")
    # "mejor", "audio" o una altura como "720p".
    p.add_argument("-c", "--calidad", default="mejor")
    p.add_argument("-o", "--carpeta", type=Path, default=Path("."))
    p.add_argument("--info", action="store_true", help="Sólo listar formatos")
    # Sin esta opción, si el archivo ya existe se aborta con error.
    p.add_argument("--sobrescribir", action="store_true")
    a = p.parse_args(argv)
    # El backend real (yt-dlp) sólo se importa al usarse.
    d = Descargador(backend or BackendYtDlp())
    try:
        if a.info:
            i = d.info(a.url)
            print(f"{i.titulo} ({i.duracion // 60}:{i.duracion % 60:02d})")
            # Listado de menor a mayor resolución; los audios (alto None → 0) van primero.
            for f in sorted(i.formatos, key=lambda f: (f.alto or 0, f.bitrate)):
                # Se marcan los formatos de sólo video, que necesitan combinarse con un audio.
                tipo = "audio" if not f.tiene_video else f"{f.alto}p" + ("" if f.tiene_audio else " (sin audio)")
                print(f"  {f.id:>6}  {f.extension:<5} {tipo}")
            return 0
        # El aviso va a stderr para no ensuciar la salida normal.
        print(AVISO, file=sys.stderr)
        ruta = d.descargar(a.url, a.calidad, a.carpeta, barra, a.sobrescribir)
        print(f"\nDescargado: {ruta}")
        return 0
    # URL ajena, calidad inválida o archivo existente → mensaje claro y exit 1.
    except (ValueError, FileExistsError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def main() -> None:
    sys.exit(ejecutar())
