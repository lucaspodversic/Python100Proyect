"""CLI.

Ejemplos::

    python -m trafico pcap captura.pcap --top 5
    python -m trafico pcap captura.pcap --json --seudonimizar
    sudo python -m trafico vivo --interfaz eth0 --paquetes 200 --filtro "tcp port 443"
    python -m trafico interfaces
"""
from __future__ import annotations

import argparse
import sys

from .analisis import Estadisticas
from .fuentes import ErrorFuente, capturar_vivo, interfaces, leer_pcap
from .informe import a_json, a_texto


def construir_parser() -> argparse.ArgumentParser:
    """Subcomandos: 'pcap' (analiza un archivo), 'vivo' (captura en una interfaz PROPIA,
    obligatoria y sin valor por defecto, con límite de paquetes y tiempo) e 'interfaces'
    (lista las disponibles).
    """
    ap = argparse.ArgumentParser(prog="trafico", description="Estadísticas de tráfico con Scapy")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for nombre in ("pcap", "vivo"):
        s = sub.add_parser(nombre)
        if nombre == "pcap":
            s.add_argument("archivo")
        else:
            s.add_argument("--interfaz", required=True, help="interfaz PROPIA (obligatoria, sin valor por defecto)")
            s.add_argument("--paquetes", type=int, default=100)
            s.add_argument("--timeout", type=float, default=30)
            s.add_argument("--filtro", help="filtro BPF, p. ej. 'tcp port 443'")
        s.add_argument("--top", type=int, default=10)
        s.add_argument("--json", action="store_true")
        s.add_argument("--seudonimizar", action="store_true", help="reemplaza IPs por seudónimos HMAC")
    sub.add_parser("interfaces")
    return ap


def main(argv: list[str] | None = None) -> int:
    """Ejecuta el subcomando. Los errores esperables (archivo inválido, sin permisos, interfaz
    inexistente) salen por stderr con código 1.
    """
    a = construir_parser().parse_args(argv)
    try:
        if a.cmd == "interfaces":
            print("\n".join(interfaces()))
            return 0
        fuente = leer_pcap(a.archivo) if a.cmd == "pcap" else capturar_vivo(
            a.interfaz, a.paquetes, a.timeout, a.filtro)
        est = Estadisticas(seudonimizar=a.seudonimizar).agregar_todos(fuente)
    except ErrorFuente as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(a_json(est, a.top) if a.json else a_texto(est, a.top), end="" if not a.json else "\n")
    return 0
