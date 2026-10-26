"""Se entrena con el corpus sintético y se evalúa en reseñas escritas a mano."""

from __future__ import annotations

from pathlib import Path

import pytest

from sentimiento import ClasificadorSentimiento, cargar_reseñas_reales, generar_corpus, normalizar
from sentimiento.cli import main


@pytest.fixture(scope="module")
def clf() -> ClasificadorSentimiento:
    # 200 reseñas sintéticas por clase = 600 de entrenamiento; se entrena una vez por módulo.
    df = generar_corpus(200)
    return ClasificadorSentimiento().entrenar(df["texto"], df["etiqueta"])


def test_normalizar() -> None:
    # Minúsculas, sin tilde, "OOOO" → "oo" y los signos ¡ ! se descartan.
    assert normalizar("¡BUENÍSIMOOOO!") == "buenisimoo"
    # "me" es transparente y "gusto" queda negado; la coma corta la ventana, por eso "pero..." no se niega.
    assert normalizar("No me gustó, pero el envío bien") == "no no_me no_gusto pero el envio bien"
    # Número, URL y mención se reemplazan por fichas genéricas (NUM, URL, USUARIO).
    assert normalizar("Pagué 1.500 en https://x.com @tienda") == "pague NUM en URL USUARIO"


def test_corpus_balanceado_y_reproducible() -> None:
    df = generar_corpus(50, semilla=3)
    # Exactamente n_por_clase por etiqueta y mismo resultado con la misma semilla.
    assert df["etiqueta"].value_counts().to_dict() == {"positivo": 50, "negativo": 50, "neutro": 50}
    assert df.equals(generar_corpus(50, semilla=3))


def test_generaliza_a_reseñas_reales(clf: ClasificadorSentimiento) -> None:
    # 54 reseñas a mano (18 por clase) con vocabulario distinto a las plantillas.
    # Umbrales: accuracy ≥ 0.75 y F1-macro ≥ 0.7 (azar con 3 clases sería ~0.33).
    ev = clf.evaluar(cargar_reseñas_reales())
    assert ev["accuracy"] >= 0.75, ev["reporte"]
    assert ev["f1_macro"] >= 0.7


def test_negacion_cambia_polaridad(clf: ClasificadorSentimiento) -> None:
    assert clf.predecir(["Me gustó mucho"]) == ["positivo"]
    # Gracias a la marca "no_" la negación invierte la predicción de la misma frase.
    assert clf.predecir(["No me gustó"]) == ["negativo"]


def test_explicabilidad_y_umbral(clf: ClasificadorSentimiento) -> None:
    claves = clf.palabras_clave(15)
    assert set(claves) == {"positivo", "negativo", "neutro"}
    # Entre las 15 palabras más negativas debe aparecer alguna de las opiniones negativas del corpus.
    assert any(w in claves["negativo"] for w in ("pesimo", "desastre", "estafa", "roto", "malisima"))
    # Una probabilidad nunca supera 1, así que con 1.01 todo cae a "neutro". Luego se restaura
    # porque el fixture es compartido por el módulo.
    clf.umbral_neutro = 1.01  # nada alcanza: todo neutro
    assert clf.predecir(["Excelente!"]) == ["neutro"]
    clf.umbral_neutro = 0.0


def test_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    modelo = tmp_path / "m.joblib"
    assert main(["entrenar", "--salida", str(modelo)]) == 0
    # CSV de 2 filas + un texto suelto: se prueban los dos modos de "clasificar" a la vez.
    (tmp_path / "in.csv").write_text("texto\nPésimo todo\nExcelente atención\n", encoding="utf-8")
    assert main(["clasificar", "--modelo", str(modelo), "--archivo", str(tmp_path / "in.csv"),
                 "--salida", str(tmp_path / "out.csv"), "Un desastre"]) == 0
    out = capsys.readouterr().out
    assert "accuracy=" in out and "negativo" in out
    assert "sentimiento" in (tmp_path / "out.csv").read_text(encoding="utf-8")
