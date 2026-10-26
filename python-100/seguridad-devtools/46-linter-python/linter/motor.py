"""Motor del linter: ejecuta reglas, aplica configuración y supresiones.

Supresión en línea: agregar `# noqa` (todas) o `# noqa: L001,L006`.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Iterable

from .reglas import REGLAS, Hallazgo

# Captura "# noqa" solo o con lista de códigos tras los dos puntos; sin distinguir mayúsculas.
NOQA = re.compile(r"#\s*noqa(?::\s*(?P<codigos>[A-Z0-9, ]+))?", re.IGNORECASE)


def _suprimido(linea: str, codigo: str) -> bool:
    """True si la línea tiene un comentario noqa que aplica al código."""
    m = NOQA.search(linea)
    if not m:
        return False
    # "# noqa" sin códigos suprime todas las reglas en esa línea.
    if not m.group("codigos"):
        return True
    # Se normaliza a mayúsculas y sin espacios: "# noqa: l001, L006" también funciona.
    return codigo in {c.strip().upper() for c in m.group("codigos").split(",")}


def analizar_codigo(codigo: str, archivo: str = "<texto>", cfg: dict | None = None) -> list[Hallazgo]:
    """Analiza un string con código Python y devuelve hallazgos ordenados."""
    cfg = cfg or {}
    # "ignorar" resta reglas; "seleccionar" (por defecto todas) define el universo inicial.
    ignorar = set(cfg.get("ignorar", []))
    seleccion = set(cfg.get("seleccionar", REGLAS.keys()))
    # Las líneas crudas sirven para reglas textuales (largo) y para buscar comentarios noqa.
    lineas = codigo.splitlines()
    try:
        arbol = ast.parse(codigo, filename=archivo)
    # Un archivo que no parsea no se puede analizar: se informa un único hallazgo E999.
    except SyntaxError as exc:
        return [Hallazgo(archivo, exc.lineno or 1, exc.offset or 0, "E999", f"error de sintaxis: {exc.msg}")]
    hallazgos: list[Hallazgo] = []
    # Cada regla es un generador de (línea, columna, mensaje).
    for cod, (_, fn) in REGLAS.items():
        if cod in ignorar or cod not in seleccion:
            continue
        for linea, col, msg in fn(arbol, lineas, cfg):
            # Las líneas del AST empiezan en 1; se protege contra números fuera de rango.
            texto = lineas[linea - 1] if 0 < linea <= len(lineas) else ""
            if not _suprimido(texto, cod):
                hallazgos.append(Hallazgo(archivo, linea, col, cod, msg))
    # set() elimina duplicados exactos; el orden (archivo, línea, columna, código) viene de order=True.
    return sorted(set(hallazgos))


def _archivos(rutas: Iterable[Path]) -> Iterable[Path]:
    """Expande directorios a sus .py, salteando venvs y cachés."""
    # Carpetas que nunca contienen código propio a revisar.
    excluir = {".venv", "venv", "__pycache__", ".git", "build", "dist"}
    for r in rutas:
        r = Path(r)
        if r.is_dir():
            for f in sorted(r.rglob("*.py")):
                # Se excluye si CUALQUIER componente de la ruta es una carpeta excluida.
                if not excluir & set(f.parts):
                    yield f
        # Archivos sueltos que no son .py se ignoran en silencio.
        elif r.suffix == ".py":
            yield r


def analizar_rutas(rutas: Iterable[Path], cfg: dict | None = None) -> list[Hallazgo]:
    """Analiza archivos y carpetas."""
    res: list[Hallazgo] = []
    for f in _archivos(rutas):
        res += analizar_codigo(f.read_text(encoding="utf-8"), str(f), cfg)
    return res


def cargar_config(pyproject: Path) -> dict:
    """Lee la sección [tool.linter] de un pyproject.toml si existe."""
    # tomllib es de la librería estándar desde Python 3.11; se importa aquí porque sólo se usa en esta función.
    import tomllib
    if not pyproject.exists():
        return {}
    with open(pyproject, "rb") as f:
        # Si falta la sección se devuelve {} y valen los valores por defecto de cada regla.
        return tomllib.load(f).get("tool", {}).get("linter", {})
