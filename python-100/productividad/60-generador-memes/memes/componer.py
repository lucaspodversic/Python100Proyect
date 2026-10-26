"""Composición del meme con Pillow.

Pasos:
1. Elegir la fuente: Impact si está instalada, si no DejaVu Sans Bold y,
   como último recurso, la fuente escalable que trae Pillow (>= 10.1).
2. Partir el texto en líneas que entren en el ancho disponible.
3. Si el bloque queda demasiado alto, achicar la fuente y repetir.
4. Dibujar centrado con contorno (`stroke_width`) para que se lea sobre
   cualquier fondo.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFont

# Primero Impact (fuente clásica de memes) en rutas típicas de Linux, macOS y Windows; DejaVu Bold como alternativa.
FUENTES_CANDIDATAS = (
    "Impact.ttf", "impact.ttf",
    "/usr/share/fonts/truetype/msttcorefonts/Impact.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Impact.ttf", "C:/Windows/Fonts/impact.ttf",
)

# Alias de tipos: una fuente y una función que la carga para un tamaño dado.
Fuente = ImageFont.FreeTypeFont
CargadorFuente = Callable[[int], Fuente]


def cargar_fuente(tamano: int, ruta: str | Path | None = None) -> Fuente:
    """Carga la fuente pedida o la primera candidata disponible."""
    # La fuente pedida por el usuario se prueba antes que las candidatas.
    for candidata in ([ruta] if ruta else []) + list(FUENTES_CANDIDATAS):
        try:
            return ImageFont.truetype(str(candidata), tamano)
        # Fuente no encontrada en esa ruta: se prueba la siguiente.
        except OSError:
            continue
    return ImageFont.load_default(size=tamano)  # Pillow >= 10.1


def ajustar_texto(texto: str, fuente: Fuente, ancho_max: int, borde: int = 0) -> list[str]:
    """Word-wrap por píxeles (no por cantidad de caracteres)."""
    # Ancho real en píxeles, incluido el contorno (getbbox → (izq, arriba, der, abajo)).
    medir = lambda t: fuente.getbbox(t, stroke_width=borde)[2]
    lineas: list[str] = []
    # Los saltos de línea del usuario se respetan; texto vacío → una línea vacía.
    for parrafo in texto.splitlines() or [""]:
        actual = ""
        for palabra in parrafo.split():
            # Se prueba agregar la palabra a la línea en curso; si no entra, se cierra la línea y empieza otra.
            prueba = f"{actual} {palabra}".strip()
            if medir(prueba) <= ancho_max or not actual:
                actual = prueba  # una palabra sola demasiado larga queda en su línea
            else:
                lineas.append(actual)
                actual = palabra
        lineas.append(actual)
    return lineas


@dataclass(frozen=True)
class EstiloMeme:
    """Parámetros visuales: mayúsculas, tamaños, márgenes y colores."""
    mayusculas: bool = True
    proporcion_tamano: float = 0.10   # tamaño inicial = alto * proporción
    tamano_minimo: int = 12
    alto_max_bloque: float = 0.30     # cada bloque ocupa como máximo 30 % del alto
    margen: float = 0.04
    color: str = "white"
    color_borde: str = "black"
    ruta_fuente: str | None = None


def _bloque(dibujo: ImageDraw.ImageDraw, texto: str, img: Image.Image, arriba: bool,
            est: EstiloMeme, cargar: CargadorFuente) -> int:
    """Dibuja un bloque de texto; devuelve el tamaño de fuente usado."""
    # Bloque vacío: no se dibuja nada.
    if not texto.strip():
        return 0
    if est.mayusculas:
        texto = texto.upper()
    # Margen proporcional al ancho para que se vea igual en imágenes chicas y grandes.
    margen = int(img.width * est.margen)
    ancho = img.width - 2 * margen
    # Tamaño inicial proporcional al alto (10 %), nunca menor que el mínimo.
    tam = max(est.tamano_minimo, int(img.height * est.proporcion_tamano))
    while True:
        fuente = cargar(tam)
        # El contorno crece con la fuente (al menos 1 px).
        borde = max(1, tam // 15)
        lineas = ajustar_texto(texto, fuente, ancho, borde)
        # Alto de línea medido con letras que suben (Á) y bajan (gj): todas las líneas usan el mismo alto.
        alto_linea = fuente.getbbox("ÁgjY", stroke_width=borde)[3] + borde
        alto_total = alto_linea * len(lineas)
        # Una palabra sola más ancha que la imagen también obliga a achicar.
        anchos_ok = all(fuente.getbbox(l, stroke_width=borde)[2] <= ancho for l in lineas)
        # Se termina si entra o si ya se llegó al mínimo (evita un bucle infinito).
        if (alto_total <= img.height * est.alto_max_bloque and anchos_ok) or tam <= est.tamano_minimo:
            break
        # Se achica un 10 % por vuelta.
        tam = max(est.tamano_minimo, int(tam * 0.9))
    # Bloque superior pegado al margen de arriba; el inferior, al de abajo.
    y = margen if arriba else img.height - margen - alto_total
    for linea in lineas:
        # Centrado horizontal línea por línea.
        w = fuente.getbbox(linea, stroke_width=borde)[2]
        dibujo.text(((img.width - w) // 2, y), linea, font=fuente, fill=est.color,
                    stroke_width=borde, stroke_fill=est.color_borde)
        y += alto_linea
    return tam


def crear_meme(imagen: Image.Image, arriba: str = "", abajo: str = "",
               estilo: EstiloMeme = EstiloMeme(), cargar: CargadorFuente | None = None) -> Image.Image:
    """Devuelve una copia RGB de la imagen con el texto agregado."""
    # Cargador inyectable: los tests usan la fuente de Pillow para resultados deterministas.
    cargar = cargar or (lambda t: cargar_fuente(t, estilo.ruta_fuente))
    img = imagen.convert("RGB")  # copia; también normaliza PNG con transparencia
    d = ImageDraw.Draw(img)
    _bloque(d, arriba, img, True, estilo, cargar)
    _bloque(d, abajo, img, False, estilo, cargar)
    return img
