"""CLI.

    python -m logweb /var/log/nginx/access.log* --top 15
    python -m logweb access.log --formato json > informe.json
    python -m logweb access.log --formato html --salida informe.html --desde 2026-10-01
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from .analisis import analizar
from .informe import a_html, a_json, a_texto
from .parser import abrir, leer


def _fecha(texto: str) -> datetime:
    """'2026-10-01' o '2026-10-01T12:00' → datetime con tz (UTC si no se indica)."""
    d = datetime.fromisoformat(texto)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def main(argv: list[str] | None = None) -> int:
    """Lee uno o más logs (texto o .gz), filtra por fechas si se pide, analiza y escribe el
    informe en texto, JSON o HTML a stdout o a un archivo. Un archivo inexistente
    termina con un error de argparse.
    """
    ap = argparse.ArgumentParser(prog="logweb", description="Analizador de logs Apache/Nginx")
    ap.add_argument("archivos", nargs="+", type=Path, help="logs (admite .gz)")
    ap.add_argument("--formato", choices=["texto", "json", "html"], default="texto")
    ap.add_argument("--salida", type=Path, help="archivo de salida (por defecto, stdout)")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--desde", type=_fecha)
    ap.add_argument("--hasta", type=_fecha)
    a = ap.parse_args(argv)

    faltan = [p for p in a.archivos if not p.is_file()]
    if faltan:
        ap.error(f"no existe: {', '.join(map(str, faltan))}")
    registros, invalidas = [], 0
    for p in a.archivos:  # varios archivos (p. ej. access.log + access.log.1.gz) se analizan juntos
        lec = leer(abrir(p))
        registros += lec.registros
        invalidas += lec.invalidas
    # Filtro de rango de fechas (inclusive en ambos extremos).
    registros = [r for r in registros if (not a.desde or r.fecha >= a.desde) and (not a.hasta or r.fecha <= a.hasta)]
    inf = analizar(registros, top=a.top, invalidas=invalidas)
    salida = {"texto": a_texto, "json": a_json, "html": a_html}[a.formato](inf)
    if a.salida:
        a.salida.write_text(salida, encoding="utf-8")
    else:
        print(salida)
    return 0
