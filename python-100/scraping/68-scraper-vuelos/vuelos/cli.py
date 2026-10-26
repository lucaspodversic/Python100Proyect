"""CLI: vuelos (--url URL | --archivo F) --perfil perfil.json [filtros] [--historial h.csv]

No hay destino por defecto: la fuente la elige el usuario y debe tener permiso
para leerla automáticamente (ver README).
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Callable, Sequence

from .cliente import BloqueadoPorRobots, ClienteEducado, ErrorHTTP
from .comparar import Criterio, HistorialPrecios, filtrar, ordenar, resumen_por_aerolinea
from .parser import PerfilVuelos, parsear_html


def _fila(v) -> str:
    """Una línea de tabla con anchos fijos para que las columnas queden alineadas."""
    esc = "directo" if v.escalas == 0 else f"{v.escalas} esc."
    # Duración como "2h05": minutos con 2 dígitos.
    return (f"{v.aerolinea:<12} {v.numero:<8} {v.origen}→{v.destino} {v.salida:%d/%m %H:%M} "
            f"{v.duracion_min // 60}h{v.duracion_min % 60:02d} {esc:<8} {v.precio:>10} {v.moneda}")


def ejecutar(argv: Sequence[str] | None = None, cliente: ClienteEducado | None = None,
             ahora: Callable[[], datetime] = datetime.now) -> int:
    """Exit codes: 0 ok, 1 error de red/archivo, 2 ningún vuelo leído, 3 robots.txt lo prohíbe."""
    p = argparse.ArgumentParser(prog="vuelos")
    # Exactamente una fuente: URL (con permiso) o archivo local guardado por el usuario.
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--url"); g.add_argument("--archivo", type=Path)
    p.add_argument("--perfil", type=Path, required=True)
    p.add_argument("--orden", choices=[c.value for c in Criterio], default="precio")
    p.add_argument("--max-escalas", type=int); p.add_argument("--precio-max", type=Decimal)
    p.add_argument("--desde-hora", type=int); p.add_argument("--hasta-hora", type=int)
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--historial", type=Path)
    a = p.parse_args(argv)
    perfil = PerfilVuelos.desde_json(a.perfil.read_text(encoding="utf-8"))
    try:
        # 5 s entre pedidos: los buscadores de vuelos son costosos de servir, se es extra prudente.
        html = (cliente or ClienteEducado(intervalo=5.0)).get(a.url).texto() if a.url else a.archivo.read_text(encoding="utf-8")
    except BloqueadoPorRobots as exc:
        # Se respeta robots.txt: no se reintenta ni se esquiva, se sugiere la vía oficial.
        print(f"robots.txt no permite {exc}; usá una API oficial", file=sys.stderr); return 3
    except (ErrorHTTP, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr); return 1
    vuelos, errores = parsear_html(html, perfil)
    for e in errores:
        print(f"⚠ {e}", file=sys.stderr)   # tarjetas rotas: aviso, no error fatal
    elegidos = ordenar(filtrar(vuelos, a.max_escalas, a.precio_max, a.desde_hora, a.hasta_hora), Criterio(a.orden))
    for v in elegidos[: a.top]:
        print(_fila(v))
    # El resumen usa todos los filtrados, no sólo el top.
    for aero, (n, minimo) in resumen_por_aerolinea(elegidos).items():
        print(f"  {aero}: {n} opción(es), desde {minimo}")
    if a.historial:
        h = HistorialPrecios(a.historial)
        # Orden importante: primero comparar contra el historial y DESPUÉS registrar;
        # al revés, el precio actual sería su propio mínimo y nunca habría bajas.
        # Se usan todos los vuelos (no sólo los filtrados) para no perder historial.
        for v, antes in h.bajas(vuelos):
            print(f"📉 {v.clave} bajó de {antes} a {v.precio} {v.moneda}")
        h.registrar(vuelos, ahora())
    return 0 if vuelos else 2


def main() -> None:
    sys.exit(ejecutar())
