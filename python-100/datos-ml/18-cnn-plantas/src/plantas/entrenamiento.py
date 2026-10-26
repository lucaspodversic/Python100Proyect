"""Entrenamiento, evaluación, predicción y persistencia."""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch import nn
from torch.utils.data import DataLoader, Dataset, TensorDataset

from .datos import imagen_a_tensor
from .modelo import RedHojas


def fijar_semillas(semilla: int) -> None:
    """Reproducibilidad en CPU."""
    # Se siembran los tres generadores (Python, NumPy, PyTorch) porque cada librería usa el suyo.
    random.seed(semilla)
    np.random.seed(semilla)
    torch.manual_seed(semilla)


@dataclass
class Historial:
    perdida_train: list[float] = field(default_factory=list)
    exactitud_val: list[float] = field(default_factory=list)
    mejor_epoca: int = -1


class Clasificador:
    def __init__(self, clases: list[str], ancho: int = 16, lado: int = 32, semilla: int = 0) -> None:
        fijar_semillas(semilla)
        self.clases, self.lado, self.ancho = list(clases), lado, ancho
        # Se guardan clases, lado y ancho porque hacen falta para reconstruir la red al cargarla.
        self.red = RedHojas(len(clases), ancho)

    # ------------------------------------------------------------ entrenamiento
    def entrenar(self, train: Dataset, val: Dataset, epocas: int = 15, lote: int = 32, lr: float = 3e-3,
                 paciencia: int = 4) -> Historial:
        """Adam + OneCycle; early stopping por exactitud de validación (se restauran los mejores pesos)."""
        # Generador propio del DataLoader: el orden de los lotes es reproducible.
        gen = torch.Generator().manual_seed(0)
        dl = DataLoader(train, batch_size=lote, shuffle=True, generator=gen)
        opt = torch.optim.AdamW(self.red.parameters(), lr=lr, weight_decay=1e-4)
        # OneCycle: el lr sube y luego baja dentro del total de pasos; converge rápido con pocas épocas.
        sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=epocas * len(dl))
        # label_smoothing: objetivos 0.95 / 0.05 en vez de 1 / 0; evita una sobreconfianza extrema.
        criterio = nn.CrossEntropyLoss(label_smoothing=0.05)
        # Se guarda una copia profunda de los pesos de la mejor época (state_dict comparte tensores con la red).
        h, mejor, sin_mejora, pesos = Historial(), -1.0, 0, copy.deepcopy(self.red.state_dict())
        for ep in range(epocas):
            self.red.train()
            total = 0.0
            for x, y in dl:
                opt.zero_grad()
                perdida = criterio(self.red(x), y)
                perdida.backward()
                opt.step()
                # OneCycleLR avanza por lote (no por época), coherente con total_steps.
                sched.step()
                # Pérdida ponderada por tamaño del lote, para que el promedio sea exacto aunque el último lote sea menor.
                total += perdida.item() * len(y)
            h.perdida_train.append(total / len(train))  # type: ignore[arg-type]
            acc = self.evaluar(val)["exactitud"]
            h.exactitud_val.append(acc)
            # Early stopping: si la exactitud de validación no mejora en `paciencia` épocas seguidas, se corta.
            if acc > mejor:
                mejor, sin_mejora, h.mejor_epoca, pesos = acc, 0, ep, copy.deepcopy(self.red.state_dict())
            else:
                sin_mejora += 1
                if sin_mejora >= paciencia:
                    break
        # Al terminar se restauran los pesos de la mejor época, no los de la última.
        self.red.load_state_dict(pesos)
        return h

    # ------------------------------------------------------------ evaluación
    @torch.no_grad()
    def _logits(self, ds: Dataset) -> tuple[torch.Tensor, torch.Tensor]:
        # eval(): BatchNorm usa estadísticas aprendidas y Dropout se desactiva.
        self.red.eval()
        xs, ys = [], []
        for x, y in DataLoader(ds, batch_size=128):
            xs.append(self.red(x))
            ys.append(torch.as_tensor(y))
        return torch.cat(xs), torch.cat(ys)

    def evaluar(self, ds: Dataset) -> dict[str, object]:
        logits, y = self._logits(ds)
        pred = logits.argmax(1)
        k = len(self.clases)
        # Matriz de confusión: fila = clase real, columna = clase predicha.
        matriz = torch.zeros(k, k, dtype=torch.long)
        for t, p in zip(y.tolist(), pred.tolist()):
            matriz[t, p] += 1
        return {"exactitud": float((pred == y).float().mean()), "matriz_confusion": matriz.tolist()}

    # ------------------------------------------------------------ predicción
    @torch.no_grad()
    def predecir_tensor(self, x: torch.Tensor) -> list[dict[str, float]]:
        self.red.eval()
        # Acepta una imagen (3, H, W) o un lote (N, 3, H, W); softmax convierte logits en probabilidades.
        probs = torch.softmax(self.red(x if x.dim() == 4 else x.unsqueeze(0)), 1)
        return [{c: float(p) for c, p in zip(self.clases, fila)} for fila in probs]

    def predecir_imagen(self, ruta: Path | str) -> tuple[str, float]:
        with Image.open(ruta) as im:
            probs = self.predecir_tensor(imagen_a_tensor(im, self.lado))[0]
        # La clase con mayor probabilidad y esa probabilidad (confianza).
        clase = max(probs, key=probs.__getitem__)
        return clase, probs[clase]

    # ------------------------------------------------------------ persistencia
    def guardar(self, ruta: Path | str) -> None:
        # Sólo pesos + metadatos (no el objeto pickled): se cargan con weights_only=True.
        torch.save({"clases": self.clases, "ancho": self.ancho, "lado": self.lado, "pesos": self.red.state_dict()}, ruta)

    @classmethod
    def cargar(cls, ruta: Path | str) -> "Clasificador":
        # weights_only=True: no ejecuta código arbitrario del archivo (a diferencia de pickle completo).
        d = torch.load(ruta, map_location="cpu", weights_only=True)
        c = cls(d["clases"], d["ancho"], d["lado"])
        c.red.load_state_dict(d["pesos"])
        return c


def dividir(x: torch.Tensor, y: torch.Tensor, frac_val: float = 0.25, semilla: int = 0) -> tuple[TensorDataset, TensorDataset]:
    # Permutación aleatoria reproducible: train y val mezclan todas las clases.
    idx = torch.randperm(len(y), generator=torch.Generator().manual_seed(semilla))
    corte = int(len(y) * (1 - frac_val))
    return TensorDataset(x[idx[:corte]], y[idx[:corte]]), TensorDataset(x[idx[corte:]], y[idx[corte:]])
