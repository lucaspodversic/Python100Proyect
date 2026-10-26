"""Tests del sincronizador con backends en memoria, carpeta y nubes falsas."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from backup_sync import (CarpetaAlmacenamiento, DriveAlmacenamiento, MemoriaAlmacenamiento,
                         S3Almacenamiento, Sincronizador)
from backup_sync.cli import main
from backup_sync.sincronizador import MANIFIESTO

from fakes import DriveFalso, S3Falso

# Instante fijo → sello de versión predecible "20240501T120000".
T0 = dt.datetime(2024, 5, 1, 12, 0, 0)


@pytest.fixture()
def origen(tmp_path: Path) -> Path:
    o = tmp_path / "docs"
    (o / "sub").mkdir(parents=True)
    (o / "a.txt").write_text("hola")
    (o / "sub" / "b.csv").write_text("1,2")
    # Origen de prueba: 2 archivos válidos (uno en subcarpeta) + un .tmp que debe excluirse.
    (o / "temp.tmp").write_text("basura")
    return o


def test_primera_sync_sube_todo_menos_excluidos(origen: Path) -> None:
    mem = MemoriaAlmacenamiento()
    # Primera sync: todo es nuevo salvo el .tmp; el manifiesto lista exactamente esos 2 archivos.
    plan = Sincronizador(origen, mem).sincronizar(ahora=T0)
    assert sorted(plan.subir) == ["a.txt", "sub/b.csv"]
    assert mem.descargar("a.txt") == b"hola" and "temp.tmp" not in mem.objetos
    assert set(json.loads(mem.descargar(MANIFIESTO))) == {"a.txt", "sub/b.csv"}


def test_sync_incremental_y_versiones(origen: Path) -> None:
    mem = MemoriaAlmacenamiento()
    s = Sincronizador(origen, mem)
    s.sincronizar(ahora=T0)
    subidas = mem.subidas
    # Incremental: sin cambios locales no se sube nada (ni siquiera el manifiesto).
    assert s.sincronizar(ahora=T0).vacio and mem.subidas == subidas  # nada que hacer
    (origen / "a.txt").write_text("chau")
    # Tras modificar a.txt: 1 actualización y 1 sin cambios (sub/b.csv); el contenido anterior
    # ("hola") queda guardado bajo el sello de T0.
    plan = s.sincronizar(ahora=T0)
    assert plan.actualizar == ["a.txt"] and plan.sin_cambios == 1
    assert mem.descargar("a.txt") == b"chau"
    assert mem.descargar("_versiones/20240501T120000/a.txt") == b"hola"


def test_dry_run_no_escribe(origen: Path) -> None:
    mem = MemoriaAlmacenamiento()
    # Dry-run: el plan dice 2 archivos a subir, pero el backend sigue vacío.
    plan = Sincronizador(origen, mem).sincronizar(dry_run=True)
    assert len(plan.subir) == 2 and mem.objetos == {}


def test_modo_espejo_borra_remoto(origen: Path) -> None:
    mem = MemoriaAlmacenamiento()
    Sincronizador(origen, mem, espejo=True).sincronizar(ahora=T0)
    (origen / "sub" / "b.csv").unlink()
    # Espejo: el borrado local se replica, pero antes se versiona la copia remota.
    plan = Sincronizador(origen, mem, espejo=True).sincronizar(ahora=T0)
    assert plan.borrar == ["sub/b.csv"] and not mem.existe("sub/b.csv")
    assert mem.existe("_versiones/20240501T120000/sub/b.csv")
    # Sin espejo no se borra nada remoto.
    mem2 = MemoriaAlmacenamiento()
    Sincronizador(origen, mem2).sincronizar()
    (origen / "a.txt").unlink()
    assert Sincronizador(origen, mem2).sincronizar().borrar == []


def test_restaurar_actual_y_version(origen: Path, tmp_path: Path) -> None:
    mem = MemoriaAlmacenamiento()
    s = Sincronizador(origen, mem)
    s.sincronizar(ahora=T0)
    (origen / "a.txt").write_text("v2")
    # Segunda corrida a las 13:00 → la versión previa de a.txt queda en _versiones/20240501T130000/.
    s.sincronizar(ahora=T0 + dt.timedelta(hours=1))
    # Restaurar lo actual devuelve los 2 archivos del manifiesto con el contenido más reciente;
    # restaurar la versión 13:00 devuelve sólo 1 archivo (el único que cambió) con su contenido viejo.
    assert s.restaurar(tmp_path / "r1") == 2 and (tmp_path / "r1" / "a.txt").read_text() == "v2"
    assert s.restaurar(tmp_path / "r2", "20240501T130000") == 1
    assert (tmp_path / "r2" / "a.txt").read_text() == "hola"


def test_backend_carpeta_y_path_traversal(origen: Path, tmp_path: Path) -> None:
    dest = CarpetaAlmacenamiento(tmp_path / "nas")
    Sincronizador(origen, dest).sincronizar()
    assert (tmp_path / "nas" / "sub" / "b.csv").read_text() == "1,2"
    with pytest.raises(ValueError):
        # Path traversal: una clave que escapa de la raíz debe rechazarse.
        dest.subir("../fuera.txt", b"x")


def test_backend_s3_falso_con_paginacion(origen: Path) -> None:
    # Con max_keys=1, listar 3 objetos (2 archivos + manifiesto) requiere 3 páginas.
    s3 = S3Falso(max_keys=1)
    dest = S3Almacenamiento(s3, "bucket", "laptop")
    Sincronizador(origen, dest).sincronizar()
    assert sorted(s3.buckets["bucket"]) == ["laptop/.backup_manifiesto.json", "laptop/a.txt", "laptop/sub/b.csv"]
    assert dest.listar() == [".backup_manifiesto.json", "a.txt", "sub/b.csv"]  # 3 páginas
    # Cada subida pidió cifrado SSE-S3.
    assert all(c["ServerSideEncryption"] == "AES256" for c in s3.llamadas_put)
    assert dest.descargar("a.txt") == b"hola"
    dest.borrar("a.txt")
    assert not dest.existe("a.txt")


def test_backend_drive_falso(origen: Path) -> None:
    drive = DriveFalso()
    # fabrica_media identidad: el "media body" son los bytes tal cual (el fake los guarda así).
    dest = DriveAlmacenamiento(drive, "CARPETA", fabrica_media=lambda b: b)
    s = Sincronizador(origen, dest)
    s.sincronizar()
    assert sorted(n for n, _ in drive.archivos.values()) == [".backup_manifiesto.json", "a.txt", "sub/b.csv"]
    (origen / "a.txt").write_text("nuevo")
    s.sincronizar(ahora=T0)
    # Actualiza el mismo archivo (no duplica) y guarda la versión anterior.
    assert [n for n, _ in drive.archivos.values()].count("a.txt") == 1
    # Una instancia nueva no tiene caché de IDs: obliga a refrescar listando la carpeta.
    nuevo = DriveAlmacenamiento(drive, "CARPETA", fabrica_media=lambda b: b)  # caché vacía
    assert nuevo.descargar("a.txt") == b"nuevo"
    nuevo.borrar("a.txt")
    assert not nuevo.existe("a.txt")


def test_cli_carpeta(origen: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Secuencia CLI: dry-run (2 nuevos), sync real excluyendo sub/* (1 nuevo: a.txt) y restauración.
    assert main([str(origen), "--carpeta", str(tmp_path / "bk"), "--dry-run"]) == 0
    assert "[dry-run] nuevos=2" in capsys.readouterr().out
    assert main([str(origen), "--carpeta", str(tmp_path / "bk"), "--excluir", "sub/*"]) == 0
    assert "nuevos=1" in capsys.readouterr().out
    assert main([str(origen), "--carpeta", str(tmp_path / "bk"), "--restaurar", str(tmp_path / "rec")]) == 0
    assert (tmp_path / "rec" / "a.txt").exists()
