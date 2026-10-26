"""Reglas del linter.

Cada regla es una función que recibe el árbol AST, las líneas del archivo
y la configuración, y devuelve hallazgos. Se registran con el decorador
`@regla(codigo, descripcion)` en el diccionario REGLAS.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Callable, Iterator

# snake_case admitiendo hasta dos guiones bajos al inicio/fin (_privada, __dunder__).
SNAKE = re.compile(r"^_{0,2}[a-z][a-z0-9_]*_{0,2}$")
# PascalCase con un guion bajo inicial opcional (_ClasePrivada).
PASCAL = re.compile(r"^_?[A-Z][A-Za-z0-9]*$")


# frozen → hasheable (se puede deduplicar con set); order → ordenable por campos en orden de declaración.
@dataclass(frozen=True, order=True)
class Hallazgo:
    """Un problema detectado en una línea/columna concreta."""

    archivo: str
    linea: int
    columna: int
    codigo: str
    mensaje: str

    def __str__(self) -> str:
        # Formato archivo:línea:columna como flake8: los editores lo convierten en enlace.
        return f"{self.archivo}:{self.linea}:{self.columna}: {self.codigo} {self.mensaje}"


# Firma común: (árbol, líneas, configuración) → iterador de (línea, columna, mensaje).
FuncionRegla = Callable[[ast.AST, list[str], dict], Iterator[tuple[int, int, str]]]
# Catálogo global código → (descripción, función), poblado por el decorador.
REGLAS: dict[str, tuple[str, FuncionRegla]] = {}


def regla(codigo: str, descripcion: str) -> Callable[[FuncionRegla], FuncionRegla]:
    """Decorador que registra una regla en el catálogo global."""
    def deco(fn: FuncionRegla) -> FuncionRegla:
        REGLAS[codigo] = (descripcion, fn)
        return fn
    return deco


@regla("L001", "except sin tipo de excepción")
def except_desnudo(arbol, lineas, cfg):
    """Detecta `except:` sin tipo, que atrapa hasta KeyboardInterrupt y SystemExit."""
    for n in ast.walk(arbol):
        # ast.walk recorre todo el árbol, incluidos bloques anidados.
        if isinstance(n, ast.ExceptHandler) and n.type is None:
            yield n.lineno, n.col_offset, "except sin tipo: capturá excepciones concretas"


@regla("L002", "argumento por defecto mutable")
def default_mutable(arbol, lineas, cfg):
    """Detecta defaults mutables: se crean una vez y se comparten entre llamadas."""
    for n in ast.walk(arbol):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Defaults posicionales y keyword-only (kw_defaults tiene None donde no hay default).
            for d in n.args.defaults + [d for d in n.args.kw_defaults if d is not None]:
                # Literales [], {}, {1} o llamadas list()/dict()/set().
                if isinstance(d, (ast.List, ast.Dict, ast.Set)) or (
                        isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id in {"list", "dict", "set"}):
                    yield d.lineno, d.col_offset, f"'{n.name}' usa un default mutable; usá None"


@regla("L003", "función demasiado larga")
def funcion_larga(arbol, lineas, cfg):
    """Detecta funciones con más líneas que el máximo configurado."""
    # 50 líneas por defecto; configurable con max_lineas_funcion.
    maximo = cfg.get("max_lineas_funcion", 50)
    for n in ast.walk(arbol):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Se cuenta desde la línea del def hasta la última del cuerpo (incluye comentarios y blancos).
            largo = (n.end_lineno or n.lineno) - n.lineno + 1
            if largo > maximo:
                yield n.lineno, n.col_offset, f"'{n.name}' tiene {largo} líneas (máx {maximo})"


@regla("L004", "función/clase pública sin docstring")
def sin_docstring(arbol, lineas, cfg):
    """Detecta funciones y clases públicas (sin "_" inicial) que no tienen docstring."""
    for n in ast.walk(arbol):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not n.name.startswith("_"):
            if ast.get_docstring(n) is None:
                yield n.lineno, n.col_offset, f"'{n.name}' no tiene docstring"


@regla("L005", "nombre que no respeta PEP 8")
def nombres(arbol, lineas, cfg):
    """Verifica snake_case en funciones y PascalCase en clases (PEP 8)."""
    for n in ast.walk(arbol):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not SNAKE.match(n.name):
            yield n.lineno, n.col_offset, f"función '{n.name}' debería ser snake_case"
        elif isinstance(n, ast.ClassDef) and not PASCAL.match(n.name):
            yield n.lineno, n.col_offset, f"clase '{n.name}' debería ser PascalCase"


@regla("L006", "import no utilizado")
def imports_sin_uso(arbol, lineas, cfg):
    """Detecta nombres importados que nunca se referencian en el módulo."""
    # nombre local → nodo del import (para informar su línea).
    importados: dict[str, ast.AST] = {}
    for n in ast.walk(arbol):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            # `from __future__ import annotations` modifica el compilador; nunca se "usa" como nombre.
            if isinstance(n, ast.ImportFrom) and n.module == "__future__":
                continue
            for alias in n.names:
                # "import os.path" liga el nombre "os"; con alias cuenta el alias.
                nombre = (alias.asname or alias.name).split(".")[0]
                # El comodín se reporta aparte (L009).
                if nombre != "*":
                    importados[nombre] = n
    # Nombres usados como variables y como base de atributos (os.path → "os").
    # Limitación conocida: nombres usados sólo dentro de strings (anotaciones diferidas) no se ven.
    usados = {n.id for n in ast.walk(arbol) if isinstance(n, ast.Name)}
    usados |= {n.value.id for n in ast.walk(arbol) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)}
    # Lo exportado en __all__ cuenta como usado
    for n in ast.walk(arbol):
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in n.targets):
            if isinstance(n.value, (ast.List, ast.Tuple)):
                usados |= {e.value for e in n.value.elts if isinstance(e, ast.Constant)}
    for nombre, nodo in importados.items():
        if nombre not in usados:
            yield nodo.lineno, nodo.col_offset, f"'{nombre}' se importa pero no se usa"


@regla("L007", "línea demasiado larga")
def linea_larga(arbol, lineas, cfg):
    """Detecta líneas más largas que max_largo_linea (100 por defecto)."""
    maximo = cfg.get("max_largo_linea", 100)
    for i, l in enumerate(lineas, start=1):
        if len(l) > maximo:
            # La columna informada es donde empieza el exceso.
            yield i, maximo, f"línea de {len(l)} caracteres (máx {maximo})"


@regla("L008", "comparación con None usando == o !=")
def comparacion_none(arbol, lineas, cfg):
    """Detecta `== None` / `!= None`: None es un singleton y se compara con `is`."""
    for n in ast.walk(arbol):
        if isinstance(n, ast.Compare):
            # Comparaciones encadenadas (a == b == None) tienen varios operadores: se revisan todos.
            for op, der in zip(n.ops, n.comparators):
                if isinstance(op, (ast.Eq, ast.NotEq)) and isinstance(der, ast.Constant) and der.value is None:
                    yield n.lineno, n.col_offset, "usá 'is None' / 'is not None'"


@regla("L009", "import con comodín")
def import_comodin(arbol, lineas, cfg):
    """Detecta `from x import *`, que oculta de dónde viene cada nombre."""
    for n in ast.walk(arbol):
        if isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names):
            yield n.lineno, n.col_offset, f"'from {n.module} import *' contamina el espacio de nombres"


@regla("L010", "print() en código (usar logging)")
def uso_print(arbol, lineas, cfg):
    """Detecta print() en código de librería (mejor usar logging)."""
    for n in ast.walk(arbol):
        # Sólo llamadas directas a print; `sys.stdout.write` u otros alias no se detectan.
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "print":
            yield n.lineno, n.col_offset, "print() encontrado; en librerías preferí logging"
