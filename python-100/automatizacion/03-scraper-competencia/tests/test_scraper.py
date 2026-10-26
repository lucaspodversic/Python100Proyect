"""Tests del scraper: fixtures HTML locales y servidor en 127.0.0.1 (sin red externa)."""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import load_workbook

from scraper_competencia import (
    BloqueadoPorRobots, FakeFetcher, HttpFetcher, ReglasSitio,
    exportar_csv, exportar_xlsx, extraer_productos, parsear_precio,
)
from scraper_competencia.cli import ejecutar
from scraper_competencia.parser import recorrer

SITIO = Path(__file__).parent / "fixtures" / "sitio"
# Selectores que coinciden con la estructura de tests/fixtures/sitio/catalogo*.html.
REGLAS = ReglasSitio(
    nombre="TiendaFicticia", tarjeta="div.producto", titulo=".titulo", precio=".precio",
    sku=".sku", enlace=".titulo a", extras={"marca": ".marca", "stock": ".stock"},
    siguiente="a.siguiente",
)


# Casos: formato es-AR con decimales, formato en-US, miles sin decimales ("45.000" = 45000),
# símbolo de euro, texto sin número (→ None) y múltiples separadores de miles.
@pytest.mark.parametrize(
    "texto,esperado",
    [("$ 12.499,90", Decimal("12499.90")), ("US$1,234.56", Decimal("1234.56")),
     ("$ 45.000", Decimal("45000")), ("€ 99", Decimal("99")), ("Consultar", None),
     ("1.234.567", Decimal("1234567"))],
)
def test_parsear_precio(texto: str, esperado: Decimal | None) -> None:
    assert parsear_precio(texto) == esperado


def test_extraer_productos_desde_fixture() -> None:
    html = (SITIO / "catalogo1.html").read_text(encoding="utf-8")
    # catalogo1 tiene 2 productos válidos + una tarjeta sin título (banner) que debe descartarse.
    prods = extraer_productos(html, REGLAS, "https://tienda.test/catalogo1.html")
    assert [p.titulo for p in prods] == ["Auriculares Inalámbricos X", "Teclado Mecánico Pro"]
    assert prods[0].precio == Decimal("12499.90")
    # El href relativo "/p/a1" se resuelve contra la URL base indicada.
    assert prods[0].url == "https://tienda.test/p/a1"
    assert prods[1].extras == {"marca": "KeyLab", "stock": "Sin stock"}


def test_recorrer_paginacion_con_fake() -> None:
    # Paginación sin red: catalogo1 enlaza a catalogo2 (que tiene 1 producto "Consultar" sin precio).
    fake = FakeFetcher({
        "https://t.test/catalogo1.html": (SITIO / "catalogo1.html").read_text(encoding="utf-8"),
        "https://t.test/catalogo2.html": (SITIO / "catalogo2.html").read_text(encoding="utf-8"),
    })
    prods = recorrer(fake, "https://t.test/catalogo1.html", REGLAS)
    # 2 productos de la página 1 + 1 de la página 2; el tercero no tiene precio publicado.
    assert len(prods) == 3 and prods[2].precio is None
    assert fake.pedidas == ["https://t.test/catalogo1.html", "https://t.test/catalogo2.html"]


def test_exportar_csv_y_xlsx_con_comparacion(tmp_path: Path) -> None:
    html = (SITIO / "catalogo1.html").read_text(encoding="utf-8")
    prods = extraer_productos(html, REGLAS)
    # Números esperados: (12499.90 − 10000) / 10000 = +25 % (la competencia es más cara);
    # para B2 el precio de la competencia es 45000 → (45000 − 50000) / 50000 = −10 %.
    propios = {"A1": Decimal("10000"), "B2": Decimal("50000")}
    with exportar_csv(prods, tmp_path / "r.csv", propios).open(encoding="utf-8-sig") as f:
        filas = list(csv.DictReader(f))
    assert float(filas[0]["diferencia_%"]) == 25.0  # 12499.90 vs 10000 -> +25%
    assert float(filas[1]["diferencia_%"]) == -10.0
    ws = load_workbook(exportar_xlsx(prods, tmp_path / "r.xlsx", propios)).active
    # D2 = columna "precio" de la primera fila de datos, ya convertida a float en el Excel.
    assert ws["A1"].value == "competidor" and ws["D2"].value == 12499.9
    assert ws.freeze_panes == "A2"


def test_http_fetcher_respeta_robots_y_ua(servidor_local: str) -> None:
    # Contra el servidor local: robots.txt de los fixtures prohíbe /privado/.
    f = HttpFetcher(intervalo_min=0)
    assert "Auriculares" in f.obtener(servidor_local + "/catalogo1.html")
    assert f.permitido(servidor_local + "/catalogo1.html")
    with pytest.raises(BloqueadoPorRobots):
        f.obtener(servidor_local + "/privado/index.html")
    assert "mailto:" in f.user_agent  # UA honesto con contacto


def test_rate_limiting_duerme_entre_peticiones(servidor_local: str) -> None:
    # El fetcher lee el reloj 2 veces por pedido (antes y después de dormir). Secuencia:
    # pedido 1 en t=0 (no espera); pedido 2 en t=0.5 → faltan 2.0 − 0.5 = 1.5 s;
    # pedido 3 en t=10 → ya pasaron más de 2 s desde el anterior, no espera.
    reloj = iter([0.0, 0.0, 0.5, 0.5, 10.0, 10.0])
    esperas: list[float] = []
    f = HttpFetcher(intervalo_min=2.0, reloj=lambda: next(reloj), dormir=esperas.append)
    f.obtener(servidor_local + "/catalogo1.html")
    f.obtener(servidor_local + "/catalogo2.html")  # a los 0.5s: debe esperar 1.5s
    f.obtener(servidor_local + "/catalogo1.html")  # a los 10s: no espera
    assert esperas == [1.5]


def test_flujo_completo_cli_contra_servidor_local(servidor_local: str, tmp_path: Path) -> None:
    # Configuración equivalente al JSON de la CLI; catalogo1 + catalogo2 dan 3 productos en total.
    config = {"sitios": [{"url": servidor_local + "/catalogo1.html", "reglas": {
        "nombre": "Local", "tarjeta": "div.producto", "titulo": ".titulo", "precio": ".precio",
        "sku": ".sku", "siguiente": "a.siguiente"}}], "propios": {"A1": "12000"}}
    n = ejecutar(config, HttpFetcher(intervalo_min=0), tmp_path / "out.xlsx")
    assert n == 3 and (tmp_path / "out.xlsx").exists()
