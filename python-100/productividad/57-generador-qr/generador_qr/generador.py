"""Generación de la imagen con `qrcode` + Pillow.

Si se agrega un logo en el centro se fuerza la corrección de errores
alta (H, ~30 %) para que el código siga siendo legible aunque el logo
tape módulos.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import qrcode
import qrcode.image.svg
from PIL import Image

# Corrección de errores: L ~7 %, M ~15 %, Q ~25 %, H ~30 % de módulos recuperables.
NIVELES = {"L": qrcode.constants.ERROR_CORRECT_L, "M": qrcode.constants.ERROR_CORRECT_M,
           "Q": qrcode.constants.ERROR_CORRECT_Q, "H": qrcode.constants.ERROR_CORRECT_H}


@dataclass(frozen=True)
class OpcionesQR:
    """Opciones visuales y de corrección del código."""
    correccion: str = "M"
    tamano_modulo: int = 10    # píxeles por módulo
    borde: int = 4             # módulos de margen (el estándar pide 4)
    color: str = "black"
    fondo: str = "white"
    logo: Path | None = None
    proporcion_logo: float = 0.22  # ancho del logo respecto del QR


def _crear(datos: str, op: OpcionesQR) -> qrcode.QRCode:
    """Construye y ajusta el objeto QRCode validando datos y nivel."""
    # Caso borde: no se genera un QR vacío.
    if not datos:
        raise ValueError("No hay contenido para codificar")
    # Con logo se fuerza H aunque se haya pedido otro nivel.
    nivel = "H" if op.logo else op.correccion
    if nivel not in NIVELES:
        raise ValueError("Corrección debe ser L, M, Q o H")
    qr = qrcode.QRCode(error_correction=NIVELES[nivel], box_size=op.tamano_modulo, border=op.borde)
    # qrcode elige solo el modo de codificación (numérico, alfanumérico o bytes).
    qr.add_data(datos)
    qr.make(fit=True)  # elige la versión (tamaño) mínima que alcanza
    return qr


def matriz(datos: str, op: OpcionesQR = OpcionesQR()) -> list[list[bool]]:
    """Matriz de módulos (True = oscuro), incluyendo el borde."""
    return _crear(datos, op).get_matrix()


def generar_imagen(datos: str, op: OpcionesQR = OpcionesQR()) -> Image.Image:
    """Imagen RGB con los colores pedidos y, opcionalmente, un logo centrado."""
    img = _crear(datos, op).make_image(fill_color=op.color, back_color=op.fondo).convert("RGB")
    if op.logo:
        # RGBA para conservar la transparencia del logo.
        logo = Image.open(op.logo).convert("RGBA")
        lado = int(img.width * op.proporcion_logo)
        # thumbnail achica manteniendo la proporción (nunca agranda).
        logo.thumbnail((lado, lado))
        # Esquina superior izquierda para que el logo quede centrado.
        pos = ((img.width - logo.width) // 2, (img.height - logo.height) // 2)
        img.paste(logo, pos, logo)  # usa el canal alfa como máscara
    return img


def guardar(datos: str, salida: Path, op: OpcionesQR = OpcionesQR()) -> Path:
    """Guarda PNG/JPG (Pillow) o SVG (vectorial) según la extensión."""
    salida = Path(salida)
    if salida.suffix.lower() == ".svg":
        # El SVG es vectorial: pegar una imagen raster ahí no está soportado.
        if op.logo:
            raise ValueError("El logo sólo está soportado en formatos raster (PNG/JPG)")
        # SvgPathImage dibuja todo como un único <path>: archivo chico y nítido a cualquier escala.
        img = _crear(datos, op).make_image(image_factory=qrcode.image.svg.SvgPathImage)
        img.save(str(salida))
    else:
        # Pillow deduce el formato (PNG/JPG) por la extensión.
        generar_imagen(datos, op).save(salida)
    return salida
