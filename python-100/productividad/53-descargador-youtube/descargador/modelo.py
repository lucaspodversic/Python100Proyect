"""Modelo y lógica pura: validación de URL, selección de formato, nombres."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

# Lista blanca exacta de hosts: rechaza dominios parecidos como youtube.com.malicioso.net.
DOMINIOS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "music.youtube.com"}
# Los IDs de YouTube tienen exactamente 11 caracteres de [A-Za-z0-9_-].
ID_VIDEO = re.compile(r"^[A-Za-z0-9_-]{11}$")


@dataclass(frozen=True)
class Formato:
    """Un formato disponible del video."""

    id: str
    extension: str
    alto: int | None        # None = sólo audio
    tiene_audio: bool
    tiene_video: bool
    bitrate: float = 0.0    # kbps (para elegir el mejor audio)
    tamano: int | None = None


@dataclass(frozen=True)
class InfoVideo:
    """Metadatos del video: ID, título, duración y formatos."""
    id: str
    titulo: str
    duracion: int  # segundos
    formatos: tuple[Formato, ...]


def validar_url(url: str) -> str:
    """Valida que sea una URL de YouTube y devuelve el ID del video."""
    # Se usa urlparse (no regex sobre el texto) para que el host se compare entero.
    u = urlparse(url.strip())
    if u.scheme not in {"http", "https"} or u.hostname not in DOMINIOS:
        raise ValueError("Sólo se aceptan URLs de YouTube")
    # Enlace corto: el ID es la ruta (youtu.be/ID).
    if u.hostname == "youtu.be":
        vid = u.path.lstrip("/")
    # /shorts/ID, /embed/ID, /live/ID: el ID es el segundo segmento.
    elif u.path.startswith(("/shorts/", "/embed/", "/live/")):
        vid = u.path.split("/")[2]
    else:
        # Formato clásico watch?v=ID; parámetros extra (t=10) se ignoran.
        vid = parse_qs(u.query).get("v", [""])[0]
    if not ID_VIDEO.match(vid):
        raise ValueError("No se encontró un ID de video válido en la URL")
    return vid


def elegir_formato(formatos: tuple[Formato, ...], calidad: str) -> list[Formato]:
    """Elige formato(s) según la calidad pedida.

    calidad: "mejor", "audio" o una altura como "720p"/"720".
    Devuelve 1 formato (progresivo o audio) o 2 (video + audio a combinar).
    Para una altura pedida se toma la mayor que no la supere.
    """
    if not formatos:
        raise ValueError("El video no tiene formatos disponibles")
    # Pistas de sólo audio, ordenadas de menor a mayor bitrate (la mejor queda al final).
    audios = sorted((f for f in formatos if f.tiene_audio and not f.tiene_video), key=lambda f: f.bitrate)
    if calidad == "audio":
        if audios:
            return [audios[-1]]
        raise ValueError("No hay pista de sólo audio")
    # Pistas con video y altura conocida.
    videos = [f for f in formatos if f.tiene_video and f.alto]
    if not videos:
        raise ValueError("No hay pistas de video")
    if calidad == "mejor":
        tope = max(f.alto for f in videos)
    else:
        # Acepta "720" o "720p" (3 o 4 dígitos).
        m = re.fullmatch(r"(\d{3,4})p?", calidad)
        if not m:
            raise ValueError("Calidad inválida: usá 'mejor', 'audio' o p. ej. '720p'")
        tope = int(m.group(1))
    # Caso borde: si ninguna altura entra en el tope se usa la más chica disponible.
    aptos = [f for f in videos if f.alto <= tope] or [min(videos, key=lambda f: f.alto)]
    alto = max(f.alto for f in aptos)
    # Todas las pistas de la mayor altura apta.
    del_alto = [f for f in aptos if f.alto == alto]
    # Preferimos un formato progresivo (video+audio) para evitar combinar
    progresivos = [f for f in del_alto if f.tiene_audio]
    if progresivos:
        return [max(progresivos, key=lambda f: f.bitrate)]
    # Sólo video: se prefiere mp4 (más compatible) y, a igualdad, el mayor bitrate.
    video = max(del_alto, key=lambda f: (f.extension == "mp4", f.bitrate))
    # Sin pista de audio separada se devuelve sólo el video.
    if not audios:
        return [video]
    # Video + mejor audio: el backend los combina (requiere ffmpeg).
    return [video, audios[-1]]


def nombre_seguro(titulo: str, extension: str, maximo: int = 120) -> str:
    """Convierte un título en nombre de archivo válido en Windows/Linux/macOS."""
    # NFKC unifica variantes Unicode (p. ej. caracteres de ancho completo).
    t = unicodedata.normalize("NFKC", titulo)
    # Caracteres prohibidos en Windows y de control → "_"; Windows tampoco admite punto o espacio al final.
    t = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", t).strip(" .")
    # Se colapsan espacios y se recorta a `maximo` caracteres (sin contar la extensión).
    t = re.sub(r"\s+", " ", t)[:maximo].rstrip(" .")
    # Caso borde: título vacío o nombre reservado de Windows → "video".
    if not t or t.upper() in {"CON", "PRN", "AUX", "NUL"}:
        t = "video"
    return f"{t}.{extension}"
