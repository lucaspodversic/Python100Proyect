"""Tests del organizador: usan carpetas temporales de pytest (tmp_path)."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from organizador import categoria_de, clasificar, deshacer, ejecutar, planificar
from organizador.cli import main

# Fecha fija (15/03/2024) para que los tests de fecha sean deterministas.
# ``mktime`` interpreta la tupla en hora LOCAL (isdst=-1 = que lo decida el SO), así que
# ``fromtimestamp`` en clasificador.py devuelve exactamente 2024-03-15 sin importar el huso.
FECHA_FIJA = time.mktime((2024, 3, 15, 12, 0, 0, 0, 0, -1))


def crear(carpeta: Path, nombre: str, contenido: bytes = b"x") -> Path:
    """Crea un archivo con fecha de modificación fija."""
    ruta = carpeta / nombre
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(contenido)
    # (atime, mtime): fijamos ambas; el clasificador usa mtime.
    os.utime(ruta, (FECHA_FIJA, FECHA_FIJA))
    return ruta


# Casos: mayúsculas en la extensión, doble extensión (.tar.gz → se mira "gz"),
# archivo sin extensión y extensión desconocida (ambos → "otros").
@pytest.mark.parametrize(
    "nombre,esperado",
    [("a.JPG", "imagenes"), ("b.pdf", "documentos"), ("c.tar.gz", "comprimidos"),
     ("d.xlsx", "hojas_calculo"), ("sin_extension", "otros"), ("e.xyz", "otros")],
)
def test_categoria_de(nombre: str, esperado: str) -> None:
    assert categoria_de(Path(nombre)) == esperado


def test_clasificar_modos(tmp_path: Path) -> None:
    # Un mismo archivo .png de 1 byte con fecha 15/03/2024 permite verificar los 4 modos:
    # tipo → imagenes, fecha → 2024/03, tipo_fecha → combinación, tamaño 1 B → "< 1 MB".
    f = crear(tmp_path, "foto.png")
    assert clasificar(f, "tipo") == Path("imagenes")
    assert clasificar(f, "fecha") == Path("2024/03")
    assert clasificar(f, "tipo_fecha") == Path("imagenes/2024/03")
    assert clasificar(f, "tamano") == Path("pequenos_<1MB")
    # Un modo inválido debe fallar fuerte, no mover archivos a una carpeta inventada.
    with pytest.raises(ValueError):
        clasificar(f, "invalido")  # type: ignore[arg-type]


def test_plan_no_modifica_disco(tmp_path: Path) -> None:
    crear(tmp_path, "a.jpg")
    crear(tmp_path, "b.pdf")
    # Dos archivos de tipos distintos → dos movimientos planificados.
    plan = planificar(tmp_path)
    assert len(plan) == 2
    # Dry-run: los archivos siguen en su lugar.
    assert (tmp_path / "a.jpg").exists() and (tmp_path / "b.pdf").exists()


def test_ejecutar_y_deshacer(tmp_path: Path) -> None:
    crear(tmp_path, "a.jpg")
    crear(tmp_path, "b.pdf")
    registro = tmp_path / "reg.json"
    # Ida y vuelta completa: mover 2 archivos y luego restaurar los 2 con el registro.
    n = ejecutar(planificar(tmp_path), registro)
    assert n == 2
    assert (tmp_path / "imagenes" / "a.jpg").exists()
    assert (tmp_path / "documentos" / "b.pdf").exists()
    # Tras deshacer, el archivo vuelve al origen y el registro se elimina.
    assert deshacer(registro) == 2
    assert (tmp_path / "a.jpg").exists() and not registro.exists()


def test_colisiones_no_sobrescriben(tmp_path: Path) -> None:
    # Ya existe imagenes/foto.jpg con otro contenido: el nuevo debe ir a "foto (1).jpg"
    # y el contenido original tiene que quedar intacto (comparamos bytes).
    crear(tmp_path, "imagenes/foto.jpg", b"original")
    crear(tmp_path, "foto.jpg", b"nuevo")
    ejecutar(planificar(tmp_path))
    assert (tmp_path / "imagenes" / "foto.jpg").read_bytes() == b"original"
    assert (tmp_path / "imagenes" / "foto (1).jpg").read_bytes() == b"nuevo"


def test_idempotente(tmp_path: Path) -> None:
    crear(tmp_path, "a.jpg")
    # Primera pasada recursiva: a.jpg va a imagenes/. En la segunda, el archivo ya está en su
    # carpeta de clasificación (archivo.parent == carpeta), así que el plan debe quedar vacío.
    ejecutar(planificar(tmp_path, recursivo=True))
    # Segunda pasada recursiva: nada para mover.
    assert planificar(tmp_path, recursivo=True) == []


def test_plantilla_renombrado(tmp_path: Path) -> None:
    crear(tmp_path, "IMG_1.JPG")
    crear(tmp_path, "IMG_2.JPG")
    # Índices 1 y 2 (orden alfabético IMG_1, IMG_2) con 3 dígitos; la extensión se agrega
    # sola en minúsculas porque la plantilla no la incluye.
    plan = planificar(tmp_path, modo="fecha", plantilla="{fecha}_{indice:03d}")
    nombres = sorted(Path(m.destino).name for m in plan)
    assert nombres == ["2024-03-15_001.jpg", "2024-03-15_002.jpg"]


def test_ocultos_ignorados(tmp_path: Path) -> None:
    # Los archivos ocultos (".algo") se ignoran por defecto para no desordenar configuraciones.
    crear(tmp_path, ".oculto.txt")
    assert planificar(tmp_path) == []
    assert len(planificar(tmp_path, incluir_ocultos=True)) == 1


def test_cli_dry_run_y_deshacer(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    crear(tmp_path, "a.mp3")
    # Recorrido completo por la CLI: dry-run (no mueve), ejecución real, deshacer,
    # y un segundo deshacer que devuelve 1 porque el registro ya no existe.
    assert main([str(tmp_path), "--dry-run"]) == 0
    assert "dry-run" in capsys.readouterr().out
    assert (tmp_path / "a.mp3").exists()
    assert main([str(tmp_path)]) == 0
    assert (tmp_path / "audio" / "a.mp3").exists()
    assert main([str(tmp_path), "--deshacer"]) == 0
    assert (tmp_path / "a.mp3").exists()
    assert main([str(tmp_path), "--deshacer"]) == 1
