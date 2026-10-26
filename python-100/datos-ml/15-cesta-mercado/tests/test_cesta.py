"""Apriori validado contra fuerza bruta y contra asociaciones plantadas."""

from __future__ import annotations

from itertools import combinations
from pathlib import Path

import pytest

from cesta import apriori, cargar_tickets, generar_reglas, generar_tickets, sugerencias_layout
from cesta.cli import main

# Ejemplo clásico de libro (5 tickets): soportes fáciles de verificar a mano.
CLASICO = [{"pan", "leche"}, {"pan", "pañales", "cerveza", "huevos"}, {"leche", "pañales", "cerveza", "cola"},
           {"pan", "leche", "pañales", "cerveza"}, {"pan", "leche", "pañales", "cola"}]


# Oráculo: prueba todos los subconjuntos posibles. Exponencial, pero exacto con pocos ítems.
def fuerza_bruta(tickets: list[set[str]], sop: float) -> dict[frozenset[str], float]:
    items = sorted(set().union(*tickets))
    res = {}
    for k in range(1, len(items) + 1):
        for comb in combinations(items, k):
            s = frozenset(comb)
            v = sum(s <= t for t in tickets) / len(tickets)
            if v >= sop:
                res[s] = v
    return res


def test_ejemplo_de_libro() -> None:
    f = apriori(CLASICO, 0.6)
    # Pañales+cerveza aparecen en los tickets 2, 3 y 4 → 3/5 = 0.6.
    assert f[frozenset({"pañales", "cerveza"})] == pytest.approx(0.6)
    assert frozenset({"pan", "leche", "pañales"}) not in f  # soporte 0.4
    reglas = {(tuple(sorted(r.antecedente)), tuple(sorted(r.consecuente))): r for r in generar_reglas(f, 0.7)}
    # Toda compra con cerveza tiene pañales → confianza 1; sop(pañales) = 4/5 = 0.8 →
    # lift = 1/0.8 = 1.25; conviction = ∞ (nunca falla); leverage = 0.6 − 0.6·0.8 = 0.12.
    r = reglas[(("cerveza",), ("pañales",))]
    assert r.confianza == 1.0 and r.lift == pytest.approx(1.25) and r.conviction == float("inf")
    assert r.leverage == pytest.approx(0.6 - 0.6 * 0.8)


# Tres umbrales: con 0.2 aparecen conjuntos de tamaño 3-4, con 0.6 casi sólo pares.
@pytest.mark.parametrize("sop", [0.2, 0.4, 0.6])
def test_igual_a_fuerza_bruta(sop: float) -> None:
    f = apriori(CLASICO, sop)
    esperado = fuerza_bruta(CLASICO, sop)
    assert f.keys() == esperado.keys()
    assert all(f[k] == pytest.approx(v) for k, v in esperado.items())


def test_igual_a_fuerza_bruta_en_datos_aleatorios() -> None:
    # Datos aleatorios: verifican el join/prune y las dos ramas de conteo con muchos casos.
    tickets = generar_tickets(300, semilla=5)
    # Restringimos a 8 productos para que la fuerza bruta (2^8 conjuntos) sea viable.
    foco = {"fernet", "coca-cola", "hielo", "pan", "leche", "yerba", "azúcar", "fideos"}
    sub = [t & foco for t in tickets if t & foco]  # sin tickets vacíos (apriori los descarta)
    assert apriori(sub, 0.03).keys() == fuerza_bruta(sub, 0.03).keys()


def test_descubre_asociaciones_plantadas() -> None:
    # Las asociaciones plantadas en PATRONES deben reaparecer con lift ≥ 2: cada acompañante
    # aparece en pocos tickets por azar, así que P(B|A) ≈ p eleva mucho el lift.
    reglas = generar_reglas(apriori(generar_tickets(2000, 1), 0.01), confianza_min=0.4, lift_min=2.0)
    pares = {(tuple(sorted(r.antecedente)), tuple(sorted(r.consecuente))) for r in reglas}
    assert (("fernet",), ("coca-cola", "hielo")) in pares
    assert (("pañales",), ("toallitas",)) in pares
    assert (("fideos",), ("salsa de tomate",)) in pares
    # Ningún par sin relación (pan/leche) con lift alto.
    # pan y leche son independientes (no hay patrón): lift ≈ 1, no debería superar 2.
    assert all({"pan", "leche"} != (r.antecedente | r.consecuente) for r in reglas)
    sug = sugerencias_layout(reglas, n=3)
    assert len(sug) == 3 and all("lift" in s for s in sug)


def test_max_tamano_y_validaciones(tmp_path: Path) -> None:
    # Sin el límite habría conjuntos de 3 con soporte 0.2; max_tamano=2 corta antes.
    assert max(len(s) for s in apriori(CLASICO, 0.2, max_tamano=2)) == 2
    assert apriori([], 0.5) == {}
    with pytest.raises(ValueError):
        apriori(CLASICO, 0)
    # Normalización: " Pan " y "PAN" → "pan"; el ticket 1 tiene dos productos y el 2 uno.
    (tmp_path / "v.csv").write_text("ticket,producto\n1, Pan \n1,leche\n2,PAN\n", encoding="utf-8")
    assert cargar_tickets(tmp_path / "v.csv") == [{"pan", "leche"}, {"pan"}]


def test_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--demo", "--salida", str(tmp_path / "r.csv")]) == 0
    out = capsys.readouterr().out
    assert "fernet" in out and "Sugerencias" in out
    assert (tmp_path / "r.csv").read_text(encoding="utf-8").startswith("antecedente,consecuente")
