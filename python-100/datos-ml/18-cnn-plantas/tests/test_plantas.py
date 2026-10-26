"""Tests de la CNN con hojas sintéticas (CPU, deterministas, ~segundos)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch
from PIL import Image

from plantas import CLASES_SINTETICAS, Clasificador, DatasetCarpetas, RedHojas, generar_hojas
from plantas.cli import main
from plantas.datos import DESVIO, MEDIA
from plantas.entrenamiento import dividir

# Pocos hilos: tests más estables en máquinas compartidas y CI.
torch.set_num_threads(2)


@pytest.fixture(scope="module")
def entrenado() -> tuple[Clasificador, torch.utils.data.Dataset]:
    # 60 hojas × 4 clases = 240 imágenes (180 train / 60 val); 12 épocas alcanzan en CPU.
    x, y = generar_hojas(60, semilla=1)
    tr, va = dividir(x, y)
    c = Clasificador(CLASES_SINTETICAS, semilla=0)
    c.historial = c.entrenar(tr, va, epocas=12)  # type: ignore[attr-defined]
    return c, va


def test_generador_forma_y_determinismo() -> None:
    x, y = generar_hojas(5, lado=32, semilla=3)
    # 5 por clase × 4 clases = 20, en orden de clase (sin mezclar).
    assert x.shape == (20, 3, 32, 32) and y.tolist() == [0] * 5 + [1] * 5 + [2] * 5 + [3] * 5
    assert torch.equal(x, generar_hojas(5, lado=32, semilla=3)[0])
    # Imagen en [0, 1] → (x − 0.5) / 0.5 ∈ [−1, 1]; 0.01 de margen por redondeo float.
    assert -1.01 <= float(x.min()) and float(x.max()) <= 1.01


def test_red_acepta_cualquier_tamano() -> None:
    # Gracias al AdaptiveAvgPool la misma red acepta 32×32 y 96×96.
    red = RedHojas(38)  # 38 clases como PlantVillage
    assert red(torch.zeros(2, 3, 32, 32)).shape == (2, 38)
    assert red(torch.zeros(1, 3, 96, 96)).shape == (1, 38)
    # Convs: 432 + 4.608 + 18.432 pesos, más BatchNorm y la lineal 64×38+38 ≈ 26 k parámetros.
    assert red.n_parametros() < 60_000


def test_aprende_las_clases(entrenado: tuple[Clasificador, torch.utils.data.Dataset]) -> None:
    c, va = entrenado
    r = c.evaluar(va)
    # Los síntomas son visualmente muy distintos: se espera alta exactitud con 4 clases.
    assert r["exactitud"] >= 0.85  # azar = 0.25
    h = c.historial  # type: ignore[attr-defined]
    assert h.perdida_train[-1] < h.perdida_train[0]
    # Cada imagen de validación aparece exactamente una vez en la matriz.
    assert sum(map(sum, r["matriz_confusion"])) == len(va)  # type: ignore[arg-type]


def test_carpetas_prediccion_y_persistencia(entrenado: tuple[Clasificador, torch.utils.data.Dataset],
                                             tmp_path: Path) -> None:
    c, _ = entrenado
    # Exporta hojas sintéticas a disco con estructura PlantVillage (clase/archivo.png).
    x, y = generar_hojas(3, semilla=7)
    for i, (img, et) in enumerate(zip(x, y)):
        carpeta = tmp_path / "ds" / CLASES_SINTETICAS[int(et)]
        carpeta.mkdir(parents=True, exist_ok=True)
        # Se deshace la normalización y se vuelve a (H, W, C) en 0-255 para guardar un PNG.
        arr = ((img * DESVIO + MEDIA).permute(1, 2, 0).numpy() * 255).round().astype(np.uint8)
        Image.fromarray(arr).save(carpeta / f"{i}.png")
    ds = DatasetCarpetas(tmp_path / "ds", lado=32, aumentar=True)
    # 3 imágenes × 4 clases = 12; las clases salen en orden alfabético de carpeta.
    assert ds.clases == sorted(CLASES_SINTETICAS) and len(ds) == 12
    xi, yi = ds[0]
    assert xi.shape == (3, 32, 32) and isinstance(yi, int)

    clase, prob = c.predecir_imagen(tmp_path / "ds" / "roya" / "3.png")
    assert clase in CLASES_SINTETICAS and 0 < prob <= 1
    c.guardar(tmp_path / "m.pt")
    otro = Clasificador.cargar(tmp_path / "m.pt")
    # Pesos guardados y cargados → probabilidades idénticas.
    assert otro.predecir_tensor(x[:2]) == c.predecir_tensor(x[:2])
    with pytest.raises(ValueError):
        # La carpeta "roya" sólo contiene archivos, sin subcarpetas de clase → ValueError.
        DatasetCarpetas(tmp_path / "ds" / "roya")


def test_cli_demo(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["demo", "--n", "20", "--salida", str(tmp_path / "m.pt")]) == 0
    assert "Exactitud val" in capsys.readouterr().out and (tmp_path / "m.pt").exists()
