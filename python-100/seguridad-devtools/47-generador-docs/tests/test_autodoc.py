"""Tests del extractor y renderizadores."""
import textwrap

from autodoc import a_html, a_markdown, extraer_modulo, extraer_paquete
from autodoc.cli import ejecutar

# Fuente de ejemplo: función con defaults, async, privada, clase con base, __init__, property y método privado.
FUENTE = textwrap.dedent('''
    """Módulo de ejemplo."""

    def sumar(a: int, b: int = 2) -> int:
        """Suma dos números."""
        return a + b

    async def bajar(url: str) -> bytes:
        """Descarga <algo>."""

    def _oculta():
        pass

    class Cuenta(Base):
        """Una cuenta bancaria."""

        def __init__(self, saldo: float = 0):
            """Crea la cuenta."""

        @property
        def saldo(self) -> float:
            """Saldo actual."""

        def _interno(self):
            pass
''')


# Sólo funciones públicas de primer nivel, firma reconstruida, async detectado y __init__ incluido.
def test_extraer():
    m = extraer_modulo(FUENTE, "ejemplo")
    assert m.docstring == "Módulo de ejemplo."
    assert [f.nombre for f in m.funciones] == ["sumar", "bajar"]
    assert m.funciones[0].firma == "sumar(a: int, b: int=2) -> int"
    assert m.funciones[1].es_async
    c = m.clases[0]
    assert c.bases == ["Base"] and [x.nombre for x in c.metodos] == ["__init__", "saldo"]
    assert c.metodos[1].decoradores == ["property"]


# Con incluir_privados aparece también _oculta.
def test_privados():
    m = extraer_modulo(FUENTE, "ejemplo", incluir_privados=True)
    assert "_oculta" in [f.nombre for f in m.funciones]


# Título, índice con ancla, firma, decorador y prefijo async en el Markdown.
def test_markdown():
    md = a_markdown([extraer_modulo(FUENTE, "ejemplo")], "API")
    assert md.startswith("# API") and "- [ejemplo](#ejemplo)" in md
    assert "### `sumar(a: int, b: int=2) -> int`" in md and "`@property`" in md
    assert "### `async bajar(url: str) -> bytes`" in md


# El "<algo>" del docstring se escapa: nada del código fuente puede inyectar marcado.
def test_html_escapa():
    h = a_html([extraer_modulo(FUENTE, "ejemplo")])
    assert "&lt;algo&gt;" in h and "<algo>" not in h
    assert h.startswith("<!doctype html>")


# Nombres con puntos y __pycache__ ignorado.
def test_paquete(tmp_path):
    pkg = tmp_path / "mipkg"; (pkg / "sub").mkdir(parents=True)
    (pkg / "__init__.py").write_text('"""Paquete raíz."""')
    (pkg / "sub" / "mod.py").write_text('def f():\n    """F."""\n')
    (pkg / "__pycache__").mkdir(); (pkg / "__pycache__" / "x.py").write_text("")
    nombres = [m.nombre for m in extraer_paquete(pkg)]
    assert nombres == ["mipkg", "mipkg.sub.mod"]


# Genera HTML en una subcarpeta que todavía no existe.
def test_cli(tmp_path):
    f = tmp_path / "m.py"; f.write_text(FUENTE)
    out = tmp_path / "docs" / "index.html"
    assert ejecutar([str(f), "-f", "html", "-o", str(out)]) == 0
    assert "Cuenta" in out.read_text()
