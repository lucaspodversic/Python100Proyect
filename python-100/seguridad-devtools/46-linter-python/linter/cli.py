"""CLI: linter RUTAS... [--ignorar L004,L010] [--max-linea 100] [--listar]."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .motor import analizar_rutas, cargar_config
from .reglas import REGLAS


def ejecutar(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="linter")
    # Sin rutas se analiza el directorio actual.
    p.add_argument("rutas", nargs="*", type=Path, default=[Path(".")])
    # Lista separada por comas, p. ej. "L004,L010".
    p.add_argument("--ignorar", default="")
    p.add_argument("--max-linea", type=int)
    p.add_argument("--json", action="store_true")
    p.add_argument("--listar", action="store_true", help="Listar reglas disponibles")
    a = p.parse_args(argv)
    # --listar sólo muestra el catálogo de reglas y sale sin analizar nada.
    if a.listar:
        for cod, (desc, _) in REGLAS.items():
            print(f"{cod}  {desc}")
        return 0
    # Precedencia: primero [tool.linter] del pyproject.toml del directorio actual, luego la CLI la pisa.
    cfg = cargar_config(Path("pyproject.toml"))
    if a.ignorar:
        # Se descartan entradas vacías ("L004,,").
        cfg["ignorar"] = [c.strip() for c in a.ignorar.split(",") if c.strip()]
    if a.max_linea:
        cfg["max_largo_linea"] = a.max_linea
    hallazgos = analizar_rutas(a.rutas, cfg)
    if a.json:
        # Hallazgo es un dataclass: __dict__ da sus campos listos para JSON.
        print(json.dumps([h.__dict__ for h in hallazgos], ensure_ascii=False, indent=2))
    else:
        for h in hallazgos:
            print(h)
        print(f"\n{len(hallazgos)} problema(s) encontrados")
    # Exit 1 si hay problemas: permite cortar un pipeline de CI.
    return 1 if hallazgos else 0


def main() -> None:
    sys.exit(ejecutar())
