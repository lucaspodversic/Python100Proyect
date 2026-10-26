"""CLI del bot. Por defecto levanta el sitio mock y corre en dry-run.

    bot-postulaciones --perfil perfil.json                 # mock propio, dry-run
    bot-postulaciones --perfil perfil.json --postular      # postula en el mock
    bot-postulaciones --perfil perfil.json --selenium      # usa Chrome real (contra el mock)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .bot import BotPostulaciones, Registro
from .navegador import HttpNavegador, Navegador, SeleniumNavegador
from .perfil import Perfil
from .sitio_mock import iniciar


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bot-postulaciones", description=__doc__)
    ap.add_argument("--perfil", type=Path, required=True, help="JSON con los campos de Perfil")
    ap.add_argument("--url", default=None, help="URL del sitio mock (sólo 127.0.0.1/localhost)")
    # Opt-in explícito: sin --postular el bot nunca envía formularios.
    ap.add_argument("--postular", action="store_true", help="desactiva dry-run")
    ap.add_argument("--max", type=int, default=5)
    ap.add_argument("--pausa", type=float, default=3.0)
    ap.add_argument("--registro", default=":memory:", help="SQLite de postulaciones")
    ap.add_argument("--selenium", action="store_true", help="usar Chrome vía Selenium")
    a = ap.parse_args(argv)
    # El perfil viene de un JSON (ver perfil.ejemplo.json); claves desconocidas → TypeError.
    perfil = Perfil(**json.loads(a.perfil.read_text(encoding="utf-8")))
    srv = None
    url = a.url
    # Sin --url se levanta el mock en un puerto libre y se usa ése: la CLI funciona "out of the box".
    if url is None:
        srv, _ = iniciar()
        url = f"http://127.0.0.1:{srv.server_address[1]}/ofertas"
    nav: Navegador
    # Import diferido: selenium es opcional y sólo se carga si se pide --selenium.
    if a.selenium:  # pragma: no cover - requiere navegador instalado
        from selenium import webdriver

        nav = SeleniumNavegador(webdriver.Chrome())
    else:
        nav = HttpNavegador()
    # Aun con --url, BotPostulaciones valida que sea loopback (lanza ValueError si no).
    bot = BotPostulaciones(nav, perfil, url, dry_run=not a.postular, max_postulaciones=a.max,
                           pausa=a.pausa, registro=Registro(a.registro))
    for r in bot.ejecutar():
        # Tres estados: se postuló, se habría postulado (dry-run) o se descartó por las reglas.
        marca = "POSTULADO" if r.postulado else ("APLICARÍA" if r.decision.aplicar else "descartada")
        print(f"[{marca:>10}] {r.oferta.id} {r.oferta.titulo} ({r.oferta.empresa}) - {'; '.join(r.decision.motivos)}")
    # Apagamos el mock sólo si lo levantó esta misma CLI.
    if srv:
        srv.shutdown()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
