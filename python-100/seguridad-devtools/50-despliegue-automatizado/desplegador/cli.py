"""CLI: desplegador [--config deploy.toml] {deploy,rollback,plan}.

`plan` (o --dry-run) muestra los comandos sin conectarse al servidor.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Sequence

from .config import ConfigDespliegue
from .conexion import ConexionDryRun, ConexionSSH
from .despliegue import Desplegador, ErrorDespliegue


# `fabrica_conexion` y `git` son inyectables: los tests nunca abren SSH ni ejecutan git real.
def ejecutar(argv: Sequence[str] | None = None, fabrica_conexion=None, git=None) -> int:
    p = argparse.ArgumentParser(prog="desplegador")
    p.add_argument("accion", choices=["deploy", "rollback", "plan"])
    # Por defecto deploy.toml en el directorio actual (ver deploy.example.toml).
    p.add_argument("--config", type=Path, default=Path("deploy.toml"))
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cfg = ConfigDespliegue.desde_toml(a.config)
    # "plan" es un atajo de "deploy --dry-run".
    dry = a.dry_run or a.accion == "plan"
    # Elección de conexión: simulada (no toca el servidor), inyectada (tests) o SSH real.
    if dry:
        cx = ConexionDryRun()
    elif fabrica_conexion:
        cx = fabrica_conexion(cfg)
    else:
        cx = ConexionSSH(cfg.host, cfg.usuario, cfg.puerto, cfg.clave_ssh)
    # Sólo se pasa git si se inyectó; si no, Desplegador usa el git local real.
    kwargs = {"git": git} if git else {}
    d = Desplegador(cfg, cx, **kwargs)
    try:
        if a.accion == "rollback":
            print(f"Rollback a {d.rollback()}")
        else:
            print(f"Release {'simulado' if dry else 'desplegado'}: {d.desplegar()}")
        # En modo simulado se lista cada comando que se habría ejecutado, para revisarlo antes.
        if dry:
            print("\nComandos que se ejecutarían:")
            for c in cx.comandos:
                print(f"  $ {c}")
        return 0
    # Cualquier paso fallido → mensaje claro y exit 1.
    except ErrorDespliegue as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    # La conexión se cierra siempre, haya error o no.
    finally:
        cx.cerrar()


def main() -> None:
    sys.exit(ejecutar())
