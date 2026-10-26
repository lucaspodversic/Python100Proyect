"""Tests: base SQLite en memoria, PDF verificado con pypdf, programador con reloj falso."""

from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

import pytest
from pypdf import PdfReader

from informes_pdf import Programacion, Repositorio, crear_base_demo, generar_informe, proxima_ejecucion
from informes_pdf.cli import main
from informes_pdf.informe import _moneda
from informes_pdf.programador import ejecutar_programado


@pytest.fixture()
def repo() -> Repositorio:
    # Base en memoria con 200 filas sintéticas (semilla fija 42): rápida y siempre igual.
    conn = sqlite3.connect(":memory:")
    crear_base_demo(conn, filas=200)
    return Repositorio(conn)


def test_kpis_consistentes(repo: Repositorio) -> None:
    k = repo.kpis("2024-01-01", "2024-12-31")
    # Todas las fechas demo son de 2024, así que el año completo incluye las 200 filas.
    assert k["operaciones"] == 200
    # Consistencia cruzada: la suma de los meses debe dar la facturación total (con tolerancia
    # porque cada mes se redondea a 2 decimales por separado).
    total_meses = sum(v for _, v in repo.ventas_por_mes("2024-01-01", "2024-12-31"))
    assert total_meses == pytest.approx(k["facturacion"], rel=1e-9)
    # Ticket promedio = facturación / operaciones (tolerancia de 1 centavo por redondeo).
    assert k["ticket_promedio"] == pytest.approx(k["facturacion"] / 200, abs=0.01)


def test_periodo_vacio(repo: Repositorio) -> None:
    # Período sin datos: COALESCE da ceros y el ticket no divide por cero.
    assert repo.kpis("2030-01-01", "2030-12-31") == {"facturacion": 0, "unidades": 0, "operaciones": 0, "ticket_promedio": 0.0}


def test_top_productos_ordenado(repo: Repositorio) -> None:
    top = repo.top_productos("2024-01-01", "2024-12-31", 3)
    # Se respeta el LIMIT y el orden descendente por facturación.
    assert len(top) == 3 and top[0][2] >= top[1][2] >= top[2][2]


def test_moneda() -> None:
    # Redondeo a 2 decimales (,891 → ,89) y separadores es-AR.
    assert _moneda(1234567.891) == "$ 1.234.567,89"


def test_genera_pdf_con_contenido(repo: Repositorio, tmp_path: Path) -> None:
    pdf = generar_informe(repo, tmp_path / "i.pdf", "2024-01-01", "2024-06-30", "Informe semestral")
    # Se verifica el PDF leyéndolo con pypdf: 2 páginas (KPIs + gráficos, y top productos).
    lector = PdfReader(str(pdf))
    assert len(lector.pages) == 2
    texto = "".join(p.extract_text() for p in lector.pages)
    assert "Informe semestral" in texto and "Facturación" in texto and "Top productos" in texto
    # El alias {nb} fue reemplazado por el total real de páginas.
    assert "Página 1/2" in texto
    # Hay imágenes (gráficos) embebidas en la primera página.
    assert len(lector.pages[0].images) == 2


def test_proxima_ejecucion_diaria_y_semanal() -> None:
    # Los cuatro casos esperados desde el lunes 4/3/2024 10:00:
    #   09:00 diario → ya pasó hoy → martes 5/3 09:00
    #   11:30 diario → todavía no pasó → hoy 11:30
    #   viernes (4) 08:00 → (4 − 0) % 7 = 4 días → viernes 8/3
    #   lunes (0) 10:00 → es exactamente ahora (no estrictamente futuro) → lunes 11/3.
    lunes_10 = dt.datetime(2024, 3, 4, 10, 0)  # lunes
    assert proxima_ejecucion(Programacion(9), lunes_10) == dt.datetime(2024, 3, 5, 9, 0)
    assert proxima_ejecucion(Programacion(11, 30), lunes_10) == dt.datetime(2024, 3, 4, 11, 30)
    assert proxima_ejecucion(Programacion(8, 0, 4), lunes_10) == dt.datetime(2024, 3, 8, 8, 0)  # viernes
    assert proxima_ejecucion(Programacion(10, 0, 0), lunes_10) == dt.datetime(2024, 3, 11, 10, 0)


def test_ejecutar_programado_con_reloj_falso() -> None:
    esperas: list[float] = []
    corridas: list[int] = []
    # El reloj falso siempre dice 09:00 → cada espera calculada es 1 h = 3600 s.
    n = ejecutar_programado(Programacion(10, 0), lambda: corridas.append(1), veces=2,
                            reloj=lambda: dt.datetime(2024, 1, 1, 9, 0), dormir=esperas.append)
    assert n == 2 and esperas == [3600.0, 3600.0] and len(corridas) == 2


def test_cli_demo(tmp_path: Path) -> None:
    # Un PDF válido siempre empieza con la firma "%PDF".
    assert main(["--demo", "-o", str(tmp_path / "x.pdf")]) == 0
    assert (tmp_path / "x.pdf").read_bytes().startswith(b"%PDF")
