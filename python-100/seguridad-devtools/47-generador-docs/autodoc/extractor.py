"""Extracción de la estructura documental de archivos Python.

Se usa `ast` en vez de importar los módulos: así NO se ejecuta código
ajeno (más seguro) y funciona aunque falten dependencias.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Funcion:
    """Función o método documentado."""

    nombre: str
    # Firma ya formateada como texto, p. ej. "sumar(a: int, b: int=2) -> int".
    firma: str
    docstring: str
    es_async: bool = False
    # Decoradores como texto (sin la "@"), en el orden en que aparecen.
    decoradores: list[str] = field(default_factory=list)


@dataclass
class Clase:
    """Clase con sus métodos públicos."""

    nombre: str
    # Clases base como texto (ast.unparse), p. ej. ["Base"] o ["abc.ABC"].
    bases: list[str]
    docstring: str
    metodos: list[Funcion] = field(default_factory=list)


@dataclass
class Modulo:
    """Módulo: docstring + clases + funciones públicas."""

    nombre: str
    docstring: str
    clases: list[Clase] = field(default_factory=list)
    funciones: list[Funcion] = field(default_factory=list)


def _firma(n: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Reconstruye la firma con anotaciones usando ast.unparse."""
    # Sólo se agrega "-> tipo" si la función tiene anotación de retorno.
    retorno = f" -> {ast.unparse(n.returns)}" if n.returns else ""
    # ast.unparse(args) reconstruye parámetros, defaults, *args y **kwargs (formato del unparser: "b: int=2").
    return f"{n.name}({ast.unparse(n.args)}){retorno}"


def _funcion(n: ast.FunctionDef | ast.AsyncFunctionDef) -> Funcion:
    """Construye el modelo Funcion a partir de un nodo def/async def."""
    return Funcion(n.name, _firma(n), ast.get_docstring(n) or "",
                   isinstance(n, ast.AsyncFunctionDef), [ast.unparse(d) for d in n.decorator_list])


def _publico(nombre: str, incluir_privados: bool) -> bool:
    """Los nombres que empiezan con _ son privados (salvo __init__)."""
    # __init__ se documenta siempre: describe cómo construir la clase.
    return incluir_privados or not nombre.startswith("_") or nombre == "__init__"


def extraer_modulo(codigo: str, nombre: str, incluir_privados: bool = False) -> Modulo:
    """Analiza el código fuente y arma el modelo Modulo."""
    # Sólo se parsea: el código analizado nunca se ejecuta.
    arbol = ast.parse(codigo)
    mod = Modulo(nombre, ast.get_docstring(arbol) or "")
    for n in arbol.body:  # sólo nivel superior (no funciones anidadas)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and _publico(n.name, incluir_privados):
            mod.funciones.append(_funcion(n))
        elif isinstance(n, ast.ClassDef) and _publico(n.name, incluir_privados):
            # Clase: bases como texto y luego sus métodos públicos (también sólo de primer nivel).
            c = Clase(n.name, [ast.unparse(b) for b in n.bases], ast.get_docstring(n) or "")
            for m in n.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and _publico(m.name, incluir_privados):
                    c.metodos.append(_funcion(m))
            mod.clases.append(c)
    return mod


def extraer_paquete(raiz: Path, incluir_privados: bool = False) -> list[Modulo]:
    """Recorre una carpeta y devuelve un Modulo por cada .py (nombre con puntos)."""
    raiz = Path(raiz)
    modulos = []
    # Orden alfabético para una documentación estable entre ejecuciones.
    for f in sorted(raiz.rglob("*.py")):
        # Se saltean cachés, entornos virtuales y tests (no son API pública).
        if any(p in {"__pycache__", ".venv", "venv", "tests"} for p in f.parts):
            continue
        # Relativo al padre de la raíz para que el nombre incluya el paquete: mipkg/sub/mod.py → mipkg.sub.mod.
        rel = f.relative_to(raiz.parent).with_suffix("")
        partes = list(rel.parts)
        # El __init__.py representa al paquete mismo: mipkg/__init__.py → "mipkg".
        if partes[-1] == "__init__":
            partes.pop()
        modulos.append(extraer_modulo(f.read_text(encoding="utf-8"), ".".join(partes), incluir_privados))
    return modulos
