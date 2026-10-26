"""CLI: generador_qr {texto,wifi,vcard,email} ... -o salida.png"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .contenidos import contenido_email, contenido_vcard, contenido_wifi
from .generador import OpcionesQR, guardar, matriz


def ascii_qr(datos: str) -> str:
    """Vista previa en terminal usando dos caracteres por módulo."""
    # Dos caracteres por módulo porque en la terminal una celda es más alta que ancha; borde 2 para no ocupar tanto.
    return "\n".join("".join("██" if m else "  " for m in fila) for fila in matriz(datos, OpcionesQR(borde=2)))


def ejecutar(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="generador_qr")
    # Las opciones globales (salida, colores, corrección, logo) van antes del subcomando.
    p.add_argument("-o", "--salida", type=Path, help="archivo .png/.jpg/.svg (si falta, muestra ASCII)")
    p.add_argument("--color", default="black"); p.add_argument("--fondo", default="white")
    # choices="LMQH": argparse acepta cada letra de la cadena como opción válida.
    p.add_argument("--correccion", default="M", choices="LMQH")
    p.add_argument("--logo", type=Path)
    # Un subcomando por tipo de contenido, cada uno con sus propios campos.
    sub = p.add_subparsers(dest="tipo", required=True)
    t = sub.add_parser("texto"); t.add_argument("contenido")
    w = sub.add_parser("wifi"); w.add_argument("ssid"); w.add_argument("--clave", default="")
    w.add_argument("--seguridad", default="WPA"); w.add_argument("--oculta", action="store_true")
    v = sub.add_parser("vcard"); v.add_argument("nombre"); v.add_argument("--apellido", default="")
    v.add_argument("--telefono", default=""); v.add_argument("--email", default="")
    v.add_argument("--organizacion", default=""); v.add_argument("--url", default="")
    e = sub.add_parser("email"); e.add_argument("destino"); e.add_argument("--asunto", default="")
    e.add_argument("--cuerpo", default="")
    a = p.parse_args(argv)
    try:
        # Primero se arma el texto a codificar según el tipo elegido.
        if a.tipo == "texto":
            datos = a.contenido
        elif a.tipo == "wifi":
            datos = contenido_wifi(a.ssid, a.clave, a.seguridad, a.oculta)
        elif a.tipo == "vcard":
            datos = contenido_vcard(a.nombre, a.apellido, a.telefono, a.email, a.organizacion, a.url)
        else:
            datos = contenido_email(a.destino, a.asunto, a.cuerpo)
        # Con -o se guarda un archivo; sin -o se muestra una vista previa ASCII.
        if a.salida:
            guardar(datos, a.salida, OpcionesQR(a.correccion, color=a.color, fondo=a.fondo, logo=a.logo))
            print(f"Guardado en {a.salida}")
        else:
            print(ascii_qr(datos))
    # Datos inválidos (p. ej. red protegida sin clave) o error al escribir o leer el logo → exit 1.
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


def main() -> None:
    sys.exit(ejecutar())
