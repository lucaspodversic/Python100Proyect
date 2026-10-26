"""Bucle principal del bot de monitoreo."""
from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
import time
from typing import Callable, Sequence

from .metricas import ProveedorLinux, ProveedorMetricas
from .notificadores import NotificadorDiscord, NotificadorSlack, TransporteHTTP
from .reglas import EvaluadorAlertas, Umbrales

# Logger con nombre propio: se puede ajustar su nivel sin afectar a otras librerías.
log = logging.getLogger("monitor")


def ciclo(proveedor: ProveedorMetricas, evaluador: EvaluadorAlertas, notificadores: list, host: str) -> int:
    """Una iteración: leer, evaluar, notificar. Devuelve alertas enviadas."""
    # Se registra cada lectura aunque no haya alertas: queda un historial en el log.
    m = proveedor.leer()
    log.info("cpu=%.1f mem=%.1f disco=%.1f", m.cpu, m.memoria, m.disco)
    enviadas = 0
    # Cada alerta se envía a todos los canales configurados; sólo se cuentan los envíos exitosos.
    for alerta in evaluador.evaluar(m):
        for n in notificadores:
            try:
                n.enviar(alerta.texto(host)); enviadas += 1
            except Exception as exc:  # un canal caído no debe tumbar el bot
                log.error("Fallo notificando: %s", exc)
    return enviadas


# `dormir` es inyectable para que los tests no esperen de verdad entre iteraciones.
def ejecutar(argv: Sequence[str] | None = None, dormir: Callable[[float], None] = time.sleep) -> int:
    p = argparse.ArgumentParser(prog="monitor")
    # Umbrales en porcentaje e intervalo entre lecturas en segundos.
    p.add_argument("--cpu", type=float, default=90); p.add_argument("--memoria", type=float, default=90)
    p.add_argument("--disco", type=float, default=85); p.add_argument("--intervalo", type=float, default=60)
    # Lecturas seguidas sobre el umbral necesarias para alertar.
    p.add_argument("--consecutivas", type=int, default=3)
    p.add_argument("--iteraciones", type=int, default=0, help="0 = infinito")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    # Un único transporte compartido por ambos notificadores.
    t = TransporteHTTP()
    notif = []
    # Los webhooks son secretos: sólo se leen de variables de entorno, nunca de argumentos (quedarían en el historial).
    if os.environ.get("SLACK_WEBHOOK_URL"):
        notif.append(NotificadorSlack(os.environ["SLACK_WEBHOOK_URL"], t))
    if os.environ.get("DISCORD_WEBHOOK_URL"):
        notif.append(NotificadorDiscord(os.environ["DISCORD_WEBHOOK_URL"], t))
    # Caso borde: sin canales el bot sigue funcionando como registrador de métricas.
    if not notif:
        log.warning("Sin webhooks configurados: sólo se registrarán métricas")
    ev = EvaluadorAlertas(Umbrales(a.cpu, a.memoria, a.disco, a.consecutivas))
    prov, host, i = ProveedorLinux(), socket.gethostname(), 0
    # iteraciones=0 → bucle infinito (modo servicio); >0 → corridas acotadas (pruebas, cron).
    while a.iteraciones == 0 or i < a.iteraciones:
        ciclo(prov, ev, notif, host); i += 1
        dormir(a.intervalo)
    return 0


def main() -> None:
    sys.exit(ejecutar())
