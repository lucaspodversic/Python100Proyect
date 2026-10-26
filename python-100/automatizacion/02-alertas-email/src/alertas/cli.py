"""CLI: ``alertas CARPETA --para a@x.com --patron "*.xlsx" --intervalo 60``.

Con ``--dry-run`` imprime los avisos por consola en lugar de enviar emails.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .notificador import FakeNotificador, SMTPConfig, SMTPNotificador
from .vigilante import Vigilante


# Hereda del fake para conservar el historial en memoria y sólo agrega la impresión:
# así --dry-run muestra exactamente el email que se habría mandado, sin abrir conexión SMTP.
class ConsolaNotificador(FakeNotificador):
    """Variante del fake que además imprime lo que se enviaría."""

    def enviar(self, asunto: str, cuerpo: str, destinatarios: list[str]) -> None:
        super().enviar(asunto, cuerpo, destinatarios)
        print(f"Para: {', '.join(destinatarios)}\nAsunto: {asunto}\n{cuerpo}\n")


def main(argv: list[str] | None = None) -> int:
    # ``action="append"`` permite repetir --para y --patron (varios destinatarios / globs).
    p = argparse.ArgumentParser(prog="alertas", description=__doc__)
    p.add_argument("carpeta", type=Path)
    p.add_argument("--para", action="append", required=True, help="destinatario (repetible)")
    p.add_argument("--patron", action="append", default=None, help="glob de archivos críticos")
    p.add_argument("--intervalo", type=float, default=60.0)
    # Sin --iteraciones el bucle es infinito (modo servicio); con un número es útil para cron o tests.
    p.add_argument("--iteraciones", type=int, default=None, help="por defecto, infinito")
    p.add_argument("--estado", type=Path, default=None, help="JSON de estado persistente")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)
    # Las credenciales SMTP nunca van por argumentos (quedarían en el historial del shell y en ``ps``):
    # se leen de variables de entorno ALERTAS_SMTP_*.
    notif = ConsolaNotificador() if a.dry_run else SMTPNotificador(SMTPConfig.desde_entorno())
    # Sin --patron se vigilan todos los archivos ("*").
    v = Vigilante(a.carpeta, notif, a.para, a.patron or ["*"], a.estado)
    v.vigilar(a.intervalo, a.iteraciones)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
