"""CLI: ``bot-swipes --edad 25 35 --distancia 20 --interes cine --interes senderismo --swipear``."""

from __future__ import annotations

import argparse

from .bot import BotSwipes
from .navegador import HttpNavegador, Navegador, SeleniumNavegador
from .preferencias import Preferencias
from .sitio_mock import iniciar


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bot-swipes", description=__doc__)
    # nargs=2: el rango de edad se pasa como dos números (mínimo y máximo).
    ap.add_argument("--edad", nargs=2, type=int, default=[18, 99])
    ap.add_argument("--distancia", type=float, default=50)
    ap.add_argument("--interes", action="append", default=[])
    ap.add_argument("--min-intereses", type=int, default=0)
    ap.add_argument("--excluir", action="append", default=[])
    ap.add_argument("--max-likes", type=int, default=20)
    ap.add_argument("--pausa", type=float, default=2.0)
    # Opt-in: sin --swipear el bot sólo muestra qué haría con el primer perfil.
    ap.add_argument("--swipear", action="store_true", help="desactiva dry-run")
    ap.add_argument("--url", default=None, help="URL de la app mock (sólo local)")
    ap.add_argument("--selenium", action="store_true")
    a = ap.parse_args(argv)
    # Orden posicional de Preferencias: edad_min, edad_max, distancia, intereses, mínimo, excluidas.
    prefs = Preferencias(a.edad[0], a.edad[1], a.distancia, a.interes, a.min_intereses, a.excluir)
    srv = None
    url = a.url
    # Sin --url se levanta la app mock local en un puerto libre.
    if url is None:
        srv, _ = iniciar()
        url = f"http://127.0.0.1:{srv.server_address[1]}/perfiles"
    nav: Navegador
    if a.selenium:  # pragma: no cover
        from selenium import webdriver

        nav = SeleniumNavegador(webdriver.Chrome())
    else:
        nav = HttpNavegador()
    # El constructor de BotSwipes vuelve a validar que la URL sea local.
    for s in BotSwipes(nav, prefs, url, dry_run=not a.swipear, max_likes=a.max_likes, pausa=a.pausa).ejecutar():
        accion = "LIKE" if s.veredicto.like else "PASS"
        print(f"{accion:4} {s.perfil.nombre} ({s.perfil.edad}) {'💘 MATCH' if s.match else ''} - {s.veredicto.motivo}"
              + ("" if s.ejecutado else " [dry-run]"))
    # Sólo se apaga el servidor si lo levantó esta CLI.
    if srv:
        srv.shutdown()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
