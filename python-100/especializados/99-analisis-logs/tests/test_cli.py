"""Tests del CLI (salida a stdout y a archivo, filtros y errores)."""
import json

import pytest

from logweb.cli import main


def test_texto_varios_archivos(apache, nginx, capsys):
    """Analizar dos archivos juntos: 16 + 6 = 22 peticiones, 1 + 1 = 2 líneas inválidas."""
    assert main([str(apache), str(nginx)]) == 0
    out = capsys.readouterr().out
    assert "Peticiones: 22" in out and "Líneas inválidas: 2" in out


def test_json_con_rango_de_fechas(apache, nginx, tmp_path):
    """--desde 2026-10-02 deja solo el día de nginx (6 válidas)."""
    destino = tmp_path / "i.json"
    assert main([str(apache), str(nginx), "--formato", "json", "--salida", str(destino), "--desde", "2026-10-02"]) == 0
    assert json.loads(destino.read_text())["peticiones"] == 6


def test_hasta_inclusive(apache, capsys):
    """--hasta 10:00 UTC incluye las dos peticiones de exactamente las 10:00:00 (escritorio y +0200)."""
    main([str(apache), "--formato", "json", "--hasta", "2026-10-01T10:00:00"])
    assert json.loads(capsys.readouterr().out)["peticiones"] == 2


def test_html(apache, tmp_path):
    """La salida HTML se escribe en el archivo pedido y es un documento completo."""
    destino = tmp_path / "i.html"
    main([str(apache), "--formato", "html", "--salida", str(destino)])
    assert destino.read_text().startswith("<!doctype html>")


def test_archivo_inexistente(tmp_path):
    """Un archivo que no existe es error de uso (argparse sale con código 2)."""
    with pytest.raises(SystemExit) as e:
        main([str(tmp_path / "no.log")])
    assert e.value.code == 2
