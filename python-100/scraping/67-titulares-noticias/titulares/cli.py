"""CLI: titulares URL_FEED... [--incluir X] [--horas 24] [--email a@b.com]

Para email: variables SMTP_HOST, SMTP_PUERTO, SMTP_USUARIO, SMTP_CLAVE, SMTP_REMITENTE.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Callable, Mapping, Sequence

from .cliente import BloqueadoPorRobots, ClienteEducado, ErrorHTTP
from .correo import Enviador, EnviadorSMTP, armar_mensaje
from .feeds import parsear_feed
from .resumen import agregar, filtrar, html_resumen, texto_resumen, ultimas_horas


def ejecutar(argv: Sequence[str] | None = None, cliente: ClienteEducado | None = None,
             enviador: Enviador | None = None, entorno: Mapping[str, str] = os.environ,
             ahora: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> int:
    """Exit codes: 0 ok (aunque algún feed falle), 1 falta config SMTP, 2 fallaron TODOS los feeds.

    `entorno` se inyecta para no depender de las variables reales en los tests.
    """
    p = argparse.ArgumentParser(prog="titulares")
    p.add_argument("feeds", nargs="+", help="URLs de feeds RSS/Atom")
    p.add_argument("--incluir", action="append", default=[]); p.add_argument("--excluir", action="append", default=[])
    p.add_argument("--horas", type=int, help="sólo noticias de las últimas N horas")
    p.add_argument("--limite", type=int, default=20)
    p.add_argument("--email", action="append", help="destinatario (repetible)")
    a = p.parse_args(argv)
    cliente = cliente or ClienteEducado(intervalo=1.0)
    listas, fallos = [], 0
    for url in a.feeds:
        try:
            # Se pasa el cuerpo en bytes: ElementTree respeta el encoding declarado en el XML.
            listas.append(parsear_feed(cliente.get(url).cuerpo))
        except (ErrorHTTP, BloqueadoPorRobots, ValueError, OSError) as exc:
            fallos += 1
            print(f"⚠ {url}: {exc}", file=sys.stderr)   # un feed caído no frena el resto
    # Orden: agregar (dedup + ordenar) → filtrar → recortar al límite.
    noticias = filtrar(agregar(listas), a.incluir, a.excluir,
                       ultimas_horas(ahora(), a.horas) if a.horas else None)[: a.limite]
    texto = texto_resumen(noticias)
    if a.email:
        if enviador is None:
            # Sin enviador inyectado se arma uno SMTP desde variables de entorno (la clave nunca va en argv).
            if "SMTP_HOST" not in entorno:
                print("Falta SMTP_HOST para enviar email", file=sys.stderr); return 1
            enviador = EnviadorSMTP(entorno["SMTP_HOST"], int(entorno.get("SMTP_PUERTO", 587)),
                                    entorno.get("SMTP_USUARIO"), entorno.get("SMTP_CLAVE"))
        msg = armar_mensaje(entorno.get("SMTP_REMITENTE", "titulares@localhost"), a.email,
                            f"Titulares {ahora():%d/%m/%Y} ({len(noticias)})", texto, html_resumen(noticias))
        enviador.enviar(msg)
        print(f"Enviado a {', '.join(a.email)}")
    else:
        print(texto)
    return 2 if fallos == len(a.feeds) else 0


def main() -> None:
    sys.exit(ejecutar())
