"""CLI. Objetivos desde --url o un JSON (--config).

config.json:
[{"nombre": "Precio", "url": "https://...", "selector": "#precio", "ignorar": ["\\d+ visitas"]}]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .cliente import BloqueadoPorRobots, ClienteEducado, ErrorHTTP
from .monitor import Monitor, Objetivo
from .notificar import NotificadorConsola, NotificadorWebhook


def ejecutar(argv: Sequence[str] | None = None, cliente: ClienteEducado | None = None,
             transporte=None, dormir=None) -> int:
    """Corre la CLI y devuelve el exit code: 0 ok, 1 error, 3 bloqueado por robots.txt.

    `cliente`, `transporte` y `dormir` se inyectan en tests para no usar red ni esperar.
    """
    p = argparse.ArgumentParser(prog="monitor_web")
    # Una sola página (--url) o varias desde archivo (--config), nunca ambas.
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--url"); g.add_argument("--config", type=Path)
    p.add_argument("--selector"); p.add_argument("--ignorar", action="append", default=[])
    p.add_argument("--estado", type=Path, default=Path(".monitor_web.json"))
    p.add_argument("--webhook", help="URL https de Slack/Discord")
    p.add_argument("--intervalo", type=float, help="vigilar cada N segundos (mínimo 60)")
    p.add_argument("--iteraciones", type=int)
    a = p.parse_args(argv)
    if a.config:
        objetivos = [Objetivo.desde_dict(d) for d in json.loads(a.config.read_text(encoding="utf-8"))]
    else:
        # Con --url el nombre del objetivo es la propia URL.
        objetivos = [Objetivo(a.url, a.url, a.selector, tuple(a.ignorar))]
    notifs: list = [NotificadorConsola()]   # la consola siempre avisa
    if a.webhook:
        kw = {"transporte": transporte} if transporte else {}
        # Discord espera el campo "content"; Slack (y la mayoría) "text".
        notifs.append(NotificadorWebhook(a.webhook, "content" if "discord" in a.webhook else "text", **kw))
    # 2 s entre pedidos al mismo host por defecto: suficiente para unos pocos objetivos.
    m = Monitor(objetivos, a.estado, cliente or ClienteEducado(intervalo=2.0), notifs)
    try:
        if a.intervalo:
            kw = {"dormir": dormir} if dormir else {}
            # Piso de 60 s: vigilar más seguido sería abusivo con el sitio ajeno.
            m.vigilar(max(60.0, a.intervalo), a.iteraciones, **kw)
        else:
            n = len(m.revisar())
            print(f"{n} cambio(s) detectado(s)")
    except BloqueadoPorRobots as exc:
        print(f"robots.txt no permite {exc}", file=sys.stderr); return 3
    except (ErrorHTTP, LookupError, ValueError, OSError, RuntimeError) as exc:
        # LookupError = selector sin coincidencias; RuntimeError = webhook rechazado.
        print(f"Error: {exc}", file=sys.stderr); return 1
    except KeyboardInterrupt:
        pass    # Ctrl+C en modo vigilancia es la forma normal de salir
    return 0


def main() -> None:
    sys.exit(ejecutar())
