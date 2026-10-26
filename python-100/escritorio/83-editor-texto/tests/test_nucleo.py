"""Tests de la lógica del editor (sin GUI)."""
import pytest

from editor.nucleo import (Documento, ErrorEditor, Recientes, buscar, estadisticas,
                           offset_a_indice_tk, reemplazar, siguiente)


def test_abrir_guardar_preserva_crlf_y_codificacion(tmp_path):
    r"""Un archivo cp1252 con CRLF ('ñ' no es UTF-8 válido así) se lee normalizado a '\n',
    recordando codificación y fin de línea; al guardar vuelve a CRLF y cp1252. La
    escritura atómica no deja temporales en la carpeta.
    """
    ruta = tmp_path / "win.txt"
    ruta.write_bytes("año\r\nñandú\r\n".encode("cp1252"))
    doc = Documento.abrir(ruta)
    assert doc.texto == "año\nñandú\n" and doc.fin_linea == "\r\n" and doc.codificacion == "cp1252"
    assert not doc.modificado
    doc.texto += "más"
    assert doc.modificado
    doc.guardar()
    assert ruta.read_bytes() == "año\r\nñandú\r\nmás".encode("cp1252")
    assert not doc.modificado
    assert [p.name for p in tmp_path.iterdir()] == ["win.txt"]  # sin temporales


def test_utf8_bom_y_guardar_como(tmp_path):
    """Un BOM UTF-8 no aparece en el texto (se detecta utf-8-sig). Guardar en otra ruta cambia
    la ruta del documento.
    """
    ruta = tmp_path / "bom.txt"
    ruta.write_bytes("\ufeffhola".encode("utf-8"))
    doc = Documento.abrir(ruta)
    assert doc.texto == "hola" and doc.codificacion == "utf-8-sig"
    otra = tmp_path / "otra.txt"
    doc.guardar(otra)
    assert otra.read_bytes() == b"hola" and doc.ruta == otra


def test_errores_abrir_y_guardar(tmp_path):
    """Bytes nulos → se rechaza como binario. Guardar un documento sin ruta y sin destino es un
    error explícito.
    """
    binario = tmp_path / "b.bin"
    binario.write_bytes(b"\x00\x01\x02")
    with pytest.raises(ErrorEditor, match="binario"):
        Documento.abrir(binario)
    with pytest.raises(ErrorEditor, match="dónde"):
        Documento(texto="x").guardar()


def test_guardado_fallido_no_rompe_original(tmp_path, monkeypatch):
    """Si falla el paso final (os.replace), el original queda intacto y el temporal se borra:
    es la razón de escribir a un temporal y renombrar.
    """
    ruta = tmp_path / "a.txt"
    ruta.write_text("original")
    doc = Documento.abrir(ruta)
    doc.texto = "nuevo"

    def explota(*_a):
        """Simula un disco lleno justo al reemplazar el archivo."""
        raise OSError("disco lleno")

    monkeypatch.setattr("editor.nucleo.os.replace", explota)
    with pytest.raises(OSError):
        doc.guardar()
    assert ruta.read_text() == "original" and len(list(tmp_path.iterdir())) == 1


def test_buscar_opciones():
    r"""En 'Casa casa CASA casamiento': sin distinguir mayúsculas hay 4; distinguiéndolas,
    'casa' en las posiciones 5-9 y 15-19 (dentro de 'casamiento'); palabra completa
    excluye 'casamiento' → 3; la regex c\w+o captura 'casamiento' (15-25). Un patrón que
    solo encuentra coincidencias vacías ('x*') devuelve [] en vez de infinitos
    hallazgos.
    """
    t = "Casa casa CASA casamiento"
    assert len(buscar(t, "casa")) == 4
    assert buscar(t, "casa", mayusculas=True) == [(5, 9), (15, 19)]
    assert len(buscar(t, "casa", palabra=True)) == 3
    assert buscar(t, r"c\w+o", regex=True) == [(15, 25)]
    assert buscar("aaa", "x*", regex=True) == []
    with pytest.raises(ErrorEditor, match="inválida"):
        buscar(t, "(", regex=True)
    with pytest.raises(ErrorEditor):
        buscar(t, "")


def test_siguiente_da_la_vuelta():
    """Desde el offset 2 el siguiente hallazgo es (5, 6); desde 6 ya no hay más y vuelve al
    primero; sin hallazgos devuelve None.
    """
    c = [(0, 1), (5, 6)]
    assert siguiente(c, 2) == (5, 6) and siguiente(c, 6) == (0, 1) and siguiente([], 0) is None


def test_reemplazar_literal_vs_regex():
    r"""En modo literal, '\1' en el reemplazo es texto (no una referencia) y '.' no es comodín.
    En modo regex los grupos sí se usan (invertir fecha). Una referencia a un grupo
    inexistente es error.
    """
    assert reemplazar("a.b a.b", "a.b", r"\1") == (r"\1 \1", 2)
    assert reemplazar("2024-01-31", r"(\d+)-(\d+)-(\d+)", r"\3/\2/\1", regex=True) == ("31/01/2024", 1)
    with pytest.raises(ErrorEditor):
        reemplazar("ab", "a", r"\9", regex=True)


def test_utilidades():
    r"""'hola mundo\nchau' = 2 líneas, 3 palabras, 15 caracteres (incluye el \n). El offset 4 en
    'ab\ncd' es la 'd': línea 2, columna 1 en notación Tk.
    """
    assert estadisticas("hola mundo\nchau") == {"lineas": 2, "palabras": 3, "caracteres": 15}
    assert estadisticas("")["lineas"] == 0
    assert offset_a_indice_tk("ab\ncd", 4) == "2.1"


def test_recientes(tmp_path):
    """Con máximo 2, agregar a, b, a, c deja [c, a] (lo último primero, sin duplicados, b se
    cae). Persiste en disco y un JSON corrupto se lee como lista vacía.
    """
    archivo = tmp_path / "cfg" / "r.json"
    r = Recientes.cargar(archivo, maximo=2)
    for n in ("a", "b", "a", "c"):
        r.agregar(tmp_path / n)
    assert [p.rsplit("/", 1)[1] for p in r.rutas] == ["c", "a"]
    assert Recientes.cargar(archivo).rutas == r.rutas
    archivo.write_text("{roto")
    assert Recientes.cargar(archivo).rutas == []
