"""Arquitectura CNN compacta (≈25 k parámetros con ancho=16).

Tres bloques Conv-BN-ReLU-MaxPool que duplican los canales, luego Global
Average Pooling (independiza del tamaño de entrada: sirve igual para 32×32
sintético o 128×128 de PlantVillage) y una capa lineal con dropout.
"""

from __future__ import annotations

import torch
from torch import nn


def _bloque(entrada: int, salida: int) -> nn.Sequential:
    # Conv 3×3 con padding 1 (conserva tamaño); sin bias porque BatchNorm ya lo incluye.
    # MaxPool2d(2) reduce a la mitad el alto y el ancho.
    return nn.Sequential(nn.Conv2d(entrada, salida, 3, padding=1, bias=False), nn.BatchNorm2d(salida),
                         nn.ReLU(inplace=True), nn.MaxPool2d(2))


class RedHojas(nn.Module):
    def __init__(self, n_clases: int, ancho: int = 16) -> None:
        super().__init__()
        # Canales 3 → 16 → 32 → 64 (con ancho=16); 32 px → 16 → 8 → 4.
        self.extractor = nn.Sequential(_bloque(3, ancho), _bloque(ancho, ancho * 2), _bloque(ancho * 2, ancho * 4))
        # Promedio global → vector de 64 sin importar el tamaño; dropout 20% contra el sobreajuste.
        self.cabeza = nn.Sequential(nn.AdaptiveAvgPool2d(1), nn.Flatten(), nn.Dropout(0.2),
                                    nn.Linear(ancho * 4, n_clases))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.cabeza(self.extractor(x))

    def n_parametros(self) -> int:
        return sum(p.numel() for p in self.parameters())
