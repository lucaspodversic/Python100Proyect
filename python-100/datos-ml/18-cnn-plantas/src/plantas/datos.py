"""Datos: generador sintético de hojas + cargador de carpetas estilo PlantVillage.

Generador sintético
-------------------
No se descarga nada para los tests. Se dibujan hojas (elipses verdes con
nervadura, rotación, tamaño y fondo aleatorios) y se les agregan síntomas:

- ``sana``        : sin manchas;
- ``roya``        : muchas pústulas chicas naranja/óxido;
- ``mancha_negra``: pocas manchas grandes, oscuras, con halo amarillo;
- ``mildiu``      : parches difusos blanquecinos/grises.

PlantVillage
------------
Dataset público (≈54.000 imágenes, 38 clases, ``Especie___Enfermedad``):
https://github.com/spMohanty/PlantVillage-Dataset (licencia CC BY-SA 3.0).
Descargarlo a mano y apuntar ``DatasetCarpetas`` a la carpeta ``color/``::

    color/
      Tomato___healthy/        img1.jpg …
      Tomato___Late_blight/    …
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch.utils.data import Dataset

CLASES_SINTETICAS = ["sana", "roya", "mancha_negra", "mildiu"]
EXTENSIONES = {".jpg", ".jpeg", ".png", ".bmp"}

# Normalización simple por canal (valores en [0,1] -> ~[-1,1]).
# Forma (3, 1, 1) para que el broadcasting la aplique por canal sobre tensores (3, H, W).
MEDIA = torch.tensor([0.5, 0.5, 0.5]).view(3, 1, 1)
DESVIO = torch.tensor([0.5, 0.5, 0.5]).view(3, 1, 1)


def _hoja(rng: np.random.Generator, lado: int) -> tuple[np.ndarray, np.ndarray]:
    """Devuelve (imagen float HxWx3, máscara bool de la hoja)."""
    # Grilla de coordenadas de cada píxel: permite dibujar figuras con fórmulas vectorizadas.
    yy, xx = np.mgrid[0:lado, 0:lado].astype(float)
    # Fondo claro de color aleatorio con una leve variación por píxel (no un color plano).
    fondo = rng.uniform(0.55, 0.85, 3) * rng.uniform(0.9, 1.0, (lado, lado, 1))
    img = np.ones((lado, lado, 3)) * fondo
    # Centro cerca del medio; semiejes a (largo) y b (ancho) y ángulo th aleatorios.
    cx, cy = lado / 2 + rng.normal(0, lado * 0.05, 2)
    a, b = lado * rng.uniform(0.32, 0.45), lado * rng.uniform(0.18, 0.26)
    th = rng.uniform(0, np.pi)
    # Coordenadas rotadas por th: la elipse (xr/a)² + (yr/b)² ≤ 1 queda inclinada.
    xr = (xx - cx) * np.cos(th) + (yy - cy) * np.sin(th)
    yr = -(xx - cx) * np.sin(th) + (yy - cy) * np.cos(th)
    mascara = (xr / a) ** 2 + (yr / b) ** 2 <= 1
    verde = np.array([rng.uniform(0.15, 0.3), rng.uniform(0.45, 0.65), rng.uniform(0.1, 0.25)])
    img[mascara] = verde * rng.uniform(0.85, 1.1)
    # Franja de ~1.6 px a lo largo del eje mayor, un 25% más clara.
    img[mascara & (np.abs(yr) < 0.8)] *= 1.25  # nervadura central
    return img, mascara


def _manchas(img: np.ndarray, mascara: np.ndarray, rng: np.random.Generator, n: int, radio: tuple[float, float],
             color: np.ndarray, halo: np.ndarray | None = None, difuso: bool = False) -> None:
    lado = img.shape[0]
    yy, xx = np.mgrid[0:lado, 0:lado]
    # Coordenadas de los píxeles de la hoja: los centros de las manchas se eligen sólo dentro de ella.
    ys, xs = np.nonzero(mascara)
    for _ in range(n):
        i = rng.integers(len(ys))
        r = rng.uniform(*radio)
        # Distancia al cuadrado al centro de la mancha (evita la raíz).
        d2 = (yy - ys[i]) ** 2 + (xx - xs[i]) ** 2
        if halo is not None:
            # El halo (más grande) se pinta primero y la mancha encima, así queda un anillo amarillo.
            img[(d2 <= (r * 1.6) ** 2) & mascara] = halo
        if difuso:
            # Mancha difusa: mezcla gaussiana (máx. 80%) con el color, sin bordes nítidos (mildiu).
            peso = np.exp(-d2 / (2 * r * r))[..., None] * 0.8 * mascara[..., None]
            img[:] = img * (1 - peso) + color * peso
        else:
            img[(d2 <= r * r) & mascara] = color


def generar_hojas(n_por_clase: int = 100, lado: int = 32, semilla: int = 0) -> tuple[torch.Tensor, torch.Tensor]:
    """Devuelve (X [N,3,lado,lado] normalizado, y [N])."""
    rng = np.random.default_rng(semilla)
    imgs, etiquetas = [], []
    for c, nombre in enumerate(CLASES_SINTETICAS):
        for _ in range(n_por_clase):
            img, m = _hoja(rng, lado)
            # Factor de escala: los radios están pensados para 32 px y crecen con imágenes más grandes.
            s = lado / 32
            if nombre == "roya":
                _manchas(img, m, rng, int(rng.integers(8, 16)), (0.8 * s, 1.5 * s), np.array([0.8, 0.45, 0.1]))
            elif nombre == "mancha_negra":
                _manchas(img, m, rng, int(rng.integers(2, 4)), (2.2 * s, 3.5 * s), np.array([0.08, 0.06, 0.04]),
                         halo=np.array([0.8, 0.75, 0.2]))
            elif nombre == "mildiu":
                _manchas(img, m, rng, int(rng.integers(2, 4)), (3 * s, 5 * s), np.array([0.85, 0.85, 0.8]), difuso=True)
            # Ruido gaussiano leve para que la red no dependa de colores exactos; clip a [0, 1].
            img = np.clip(img + rng.normal(0, 0.03, img.shape), 0, 1)  # ruido de sensor
            imgs.append(img)
            etiquetas.append(c)
    # NumPy usa (N, H, W, C) y PyTorch espera (N, C, H, W).
    x = torch.tensor(np.stack(imgs), dtype=torch.float32).permute(0, 3, 1, 2)
    return (x - MEDIA) / DESVIO, torch.tensor(etiquetas)


def imagen_a_tensor(img: Image.Image, lado: int) -> torch.Tensor:
    # convert("RGB") unifica PNG con transparencia o grises; se escala a lado × lado y a [0, 1].
    arr = np.asarray(img.convert("RGB").resize((lado, lado), Image.BILINEAR), dtype=np.float32) / 255.0
    return (torch.from_numpy(arr).permute(2, 0, 1) - MEDIA) / DESVIO


class DatasetCarpetas(Dataset):
    """Lee ``raiz/<clase>/*.jpg`` (formato PlantVillage / ImageFolder) sin depender de torchvision."""

    def __init__(self, raiz: Path | str, lado: int = 64, aumentar: bool = False, semilla: int = 0) -> None:
        self.raiz = Path(raiz)
        # Cada subcarpeta es una clase; ordenadas para que el índice de clase sea estable.
        self.clases = sorted(p.name for p in self.raiz.iterdir() if p.is_dir())
        if not self.clases:
            raise ValueError(f"{raiz} no tiene subcarpetas de clases")
        # Sólo archivos con extensión de imagen (se ignoran .txt, .DS_Store, etc.).
        self.muestras = [(f, i) for i, c in enumerate(self.clases) for f in sorted((self.raiz / c).iterdir())
                         if f.suffix.lower() in EXTENSIONES]
        self.lado, self.aumentar = lado, aumentar
        self._rng = np.random.default_rng(semilla)

    def __len__(self) -> int:
        return len(self.muestras)

    def __getitem__(self, i: int) -> tuple[torch.Tensor, int]:
        ruta, y = self.muestras[i]
        # Se lee cada imagen bajo demanda (no se carga todo el dataset en memoria).
        with Image.open(ruta) as im:
            x = imagen_a_tensor(im, self.lado)
        if self.aumentar:  # aumentos baratos: espejos horizontales/verticales
            if self._rng.random() < 0.5:
                # flip(2) = espejo horizontal (eje W), flip(1) = vertical (eje H). Una hoja enferma lo sigue estando.
                x = x.flip(2)
            if self._rng.random() < 0.5:
                x = x.flip(1)
        return x, y
