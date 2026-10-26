"""Tests de cada regla con fragmentos de código mínimos."""
import textwrap

import pytest

from linter import REGLAS, analizar_codigo, analizar_rutas
from linter.cli import ejecutar


def codigos(src: str, **cfg) -> list[str]:
    """Analiza `src` dedentado e ignora L004/L010 para que cada test aísle su regla."""
    return [h.codigo for h in analizar_codigo(textwrap.dedent(src), cfg={"ignorar": ["L004", "L010"], **cfg})]


# Las 10 reglas L001-L010 quedaron registradas por el decorador.
def test_catalogo_completo():
    assert len(REGLAS) == 10


def test_except_desnudo():
    assert codigos("try:\n    pass\nexcept:\n    pass\n") == ["L001"]


# Tres defaults mutables: lista literal, dict() y set literal keyword-only.
def test_default_mutable():
    assert codigos("def f(a=[], b=dict(), *, c={}):\n    return a\n").count("L002") == 3


# La función ocupa 6 líneas (def + 5) con máximo 3.
def test_funcion_larga():
    cuerpo = "def f():\n" + "    x = 1\n" * 5
    assert "L003" in codigos(cuerpo, max_lineas_funcion=3)


# Sólo la función pública sin docstring; la privada y la clase documentada no cuentan.
def test_docstring():
    hs = analizar_codigo('def publica():\n    pass\n\ndef _privada():\n    pass\n\nclass A:\n    """doc"""\n')
    assert [h.codigo for h in hs] == ["L004"]


# Función en PascalCase y clase en snake_case: dos L005.
def test_nombres():
    assert codigos("def MiFuncion():\n    pass\n\nclass mala_clase:\n    pass\n") == ["L005", "L005"]


# sys se usa; os y el alias z no.
def test_import_sin_uso():
    src = "import os\nimport sys\nfrom x import y as z\nprint(sys.argv)\n"
    hs = analizar_codigo(src, cfg={"seleccionar": ["L006"]})
    assert [h.mensaje.split("'")[1] for h in hs] == ["os", "z"]


# Reexportar vía __all__ cuenta como uso (típico de __init__.py).
def test_import_en_all_cuenta_como_usado():
    assert codigos("from .m import f\n__all__ = ['f']\n") == []


# 9 + 100 = 109 caracteres > 100.
def test_linea_larga():
    assert codigos("x = 1  # " + "a" * 100 + "\n") == ["L007"]


def test_none():
    assert codigos("x = 1\nif x == None:\n    pass\n") == ["L008"]


def test_comodin():
    assert "L009" in codigos("from os import *\n")


def test_print():
    assert [h.codigo for h in analizar_codigo("print(1)\n", cfg={"seleccionar": ["L010"]})] == ["L010"]


# Supresión por código concreto y supresión total.
def test_noqa():
    assert codigos("try:\n    pass\nexcept:  # noqa: L001\n    pass\n") == []
    assert codigos("import os  # noqa\n") == []


# Código inválido → E999 en vez de una excepción.
def test_sintaxis():
    assert codigos("def (:\n") == ["E999"]


# La carpeta .venv se saltea: sólo malo.py reporta; exit 0 sin problemas y 1 con problemas.
def test_rutas_y_cli(tmp_path, capsys):
    (tmp_path / "ok.py").write_text('"""m"""\n')
    (tmp_path / "malo.py").write_text("import os\n")
    (tmp_path / ".venv").mkdir(); (tmp_path / ".venv" / "x.py").write_text("import os\n")
    assert [h.codigo for h in analizar_rutas([tmp_path])] == ["L006"]
    assert ejecutar([str(tmp_path / "ok.py")]) == 0
    assert ejecutar([str(tmp_path)]) == 1
    assert ejecutar(["--listar"]) == 0


# Un módulo correcto (docstrings, snake_case, import usado) no produce ningún hallazgo.
def test_codigo_limpio_no_reporta():
    src = '''
    """Módulo de ejemplo."""
    import os


    def ruta_casa() -> str:
        """Devuelve HOME."""
        return os.environ.get("HOME", "")
    '''
    assert analizar_codigo(textwrap.dedent(src)) == []
