"""Tests sobre un corpus chico de 4 documentos incluido en tests/corpus (sin red)."""
from pathlib import Path

import pytest

from buscador.cli import main
from buscador.consulta import parsear
from buscador.indice import Indice, fragmento
from buscador.texto import plegar, raiz, terminos

CORPUS = Path(__file__).parent / "corpus"


@pytest.fixture
def indice():
    """Índice del corpus de prueba."""
    ind = Indice()
    ind.indexar_carpeta(CORPUS)
    return ind


def test_normalizacion_y_stemming():
    """Se quitan tildes pero se conserva la ñ; el stemmer liviano lleva
    programación/programaciones/programar a 'program'; las stopwords (la, de, los) no
    son términos; las palabras cortas no se recortan.
    """
    assert plegar("Canción ÑANDÚ") == "cancion ñandu"
    assert raiz(plegar("programación")) == raiz("programaciones") == raiz("programar") == "program"
    assert terminos("La base de los datos") == ["bas", "dat"]
    assert raiz("sol") == "sol"   # raíz mínima: no recorta palabras cortas


def test_parsear_consulta():
    """'mongo' queda como 'mong' (stem). En 'base de datos', 'de' es stopword pero deja hueco:
    dat en posición 2. Una consulta de solo stopwords queda vacía.
    """
    c = parsear('python +sql -mongo "base de datos"')
    assert c.opcionales == ["python"] and c.obligatorios == ["sql"] and c.excluidos == ["mong"]
    assert c.frases == [[("bas", 0), ("dat", 2)]]
    assert parsear("de la el").vacia


def test_ranking_relevancia(indice):
    """El documento de Python gana para 'python programación' y los puntajes vienen en orden
    descendente.
    """
    res = indice.buscar("python programación")
    assert res[0].doc_id == "python.md"
    assert res[0].titulo == "Introducción a Python"
    assert [r.puntuacion for r in res] == sorted((r.puntuacion for r in res), reverse=True)


def test_sin_tildes_encuentra_con_tildes(indice):
    """'introduccion' sin tilde encuentra 'Introducción'."""
    assert indice.buscar("introduccion")[0].doc_id == "python.md"


def test_frase_exacta_y_exclusion(indice):
    """La frase aparece en bases.txt y nosql.md; excluir mongodb deja solo bases.txt; invertir
    el orden ('datos base') no encuentra nada.
    """
    ids = {r.doc_id for r in indice.buscar('"base de datos"')}
    assert ids == {"bases.txt", "nosql.md"}
    assert {r.doc_id for r in indice.buscar('"base de datos" -mongodb')} == {"bases.txt"}
    assert indice.buscar('"datos base"') == []   # el orden importa


def test_obligatorio(indice):
    """Varios documentos tienen 'datos', pero +empanadas deja solo la receta."""
    assert {r.doc_id for r in indice.buscar("datos +empanadas")} == {"cocina.txt"}


def test_bm25_satura_y_titulo_pesa(indice):
    """nosql.md repite 'datos' muchas veces, pero BM25 satura la frecuencia, y bases.txt gana
    por tener los tres términos y 'bases' en el título.
    """
    # nosql.md repite "datos" muchas veces, pero bases.txt lo tiene en el título junto a "bases".
    res = indice.buscar("bases datos relacionales")
    assert res[0].doc_id == "bases.txt"


def test_fragmento_resalta():
    """Fragmento con ventana de 3 palabras alrededor de la coincidencia, que se resalta entre
    corchetes y lleva '…' porque corta el principio.
    """
    f = fragmento("uno dos tres Python cuatro cinco seis", {"python"}, ventana=3)
    assert "[Python]" in f and f.startswith("…")


def test_indexacion_incremental_y_persistencia(tmp_path):
    """Se indexan solo .txt y .md (2 nuevos). Al borrar a.txt el siguiente reindexado lo
    elimina y desaparece hasta el término 'gat'. El título sale del encabezado Markdown
    y se conserva al guardar y cargar.
    """
    (tmp_path / "a.txt").write_text("gatos y perros", encoding="utf-8")
    (tmp_path / "b.md").write_text("# Loros\nloros parlanchines", encoding="utf-8")
    (tmp_path / "ignorar.bin").write_bytes(b"\x00")
    ind = Indice()
    assert ind.indexar_carpeta(tmp_path) == {"nuevos": 2, "actualizados": 0, "sin_cambios": 0, "eliminados": 0}
    (tmp_path / "a.txt").unlink()
    assert ind.indexar_carpeta(tmp_path)["eliminados"] == 1
    assert ind.buscar("gatos") == [] and "gat" not in ind.postings
    ruta = tmp_path / "i.json"
    ind.guardar(ruta)
    assert Indice.cargar(ruta).buscar("loro")[0].titulo == "Loros"


def test_cli(tmp_path, capsys):
    """Buscar sin índice da 1; indexar informa los 4 documentos; buscar muestra el título."""
    idx = tmp_path / "i.json"
    assert main(["--indice", str(idx), "buscar", "x"]) == 1
    assert main(["--indice", str(idx), "indexar", str(CORPUS)]) == 0
    assert "4 documentos" in capsys.readouterr().out
    assert main(["--indice", str(idx), "buscar", "empanadas"]) == 0
    assert "Receta de empanadas" in capsys.readouterr().out
