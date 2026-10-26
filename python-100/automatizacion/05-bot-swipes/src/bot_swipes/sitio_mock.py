"""App de citas MOCK servida en 127.0.0.1 (perfiles ficticios).

Rutas:
- ``GET /perfiles``  muestra el siguiente perfil pendiente (o ``.sin-perfiles``)
- ``POST /swipe``    recibe ``id`` y ``accion`` (``like``/``pass``)

Algunos perfiles tienen ``match=True`` (like mutuo predefinido) para que la
respuesta muestre ``.match`` de forma determinista.
"""

from __future__ import annotations

import argparse
import html
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

# Perfiles diseñados para ejercitar cada regla: p2 por edad, p3 por distancia, p4 sin bio,
# p5 con palabra excluida, p6 con interés en mayúsculas. "match" fija la respuesta del mock.
PERFILES_DEMO: list[dict[str, object]] = [
    {"id": "p1", "nombre": "Alex", "edad": 29, "distancia": 5, "bio": "Amo el senderismo y la fotografía",
     "intereses": ["senderismo", "fotografía", "cine"], "match": True},
    {"id": "p2", "nombre": "Sam", "edad": 45, "distancia": 3, "bio": "Cocinero amateur",
     "intereses": ["cocina"], "match": False},
    {"id": "p3", "nombre": "Robin", "edad": 31, "distancia": 120, "bio": "Viajero",
     "intereses": ["viajes", "cine"], "match": True},
    {"id": "p4", "nombre": "Charlie", "edad": 27, "distancia": 8, "bio": "",
     "intereses": ["música", "cine"], "match": False},
    {"id": "p5", "nombre": "Jordan", "edad": 33, "distancia": 12, "bio": "Fumador social, me gusta el cine",
     "intereses": ["cine", "senderismo"], "match": False},
    {"id": "p6", "nombre": "Dani", "edad": 30, "distancia": 2, "bio": "Lectora y montañista",
     "intereses": ["Senderismo", "lectura"], "match": False},
]


@dataclass
class EstadoApp:
    perfiles: list[dict[str, object]] = field(default_factory=lambda: [dict(p) for p in PERFILES_DEMO])
    swipes: list[tuple[str, str]] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    # El siguiente perfil pendiente es el primero que todavía no recibió swipe.
    def pendiente(self) -> dict[str, object] | None:
        vistos = {pid for pid, _ in self.swipes}
        return next((p for p in self.perfiles if p["id"] not in vistos), None)


def _html(cuerpo: str) -> bytes:
    return f"<!doctype html><html lang='es'><head><meta charset='utf-8'><title>CitasMock</title></head><body>{cuerpo}</body></html>".encode()


def crear_handler(estado: EstadoApp) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a: object) -> None:
            pass

        def _ok(self, contenido: bytes, codigo: int = 200) -> None:
            self.send_response(codigo)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(contenido)))
            self.end_headers()
            self.wfile.write(contenido)

        # ``extra`` permite anteponer el aviso de match a la tarjeta del siguiente perfil.
        def _tarjeta(self, extra: str = "") -> bytes:
            p = estado.pendiente()
            if p is None:
                return _html(extra + "<p class='sin-perfiles'>No hay más perfiles</p>")
            intereses = "".join(f"<li>{html.escape(str(i))}</li>" for i in p["intereses"])  # type: ignore[union-attr]
            return _html(
                extra + f"<section class='perfil' data-id='{p['id']}'><h2 class='nombre'>{html.escape(str(p['nombre']))}</h2>"
                f"<span class='edad'>{p['edad']}</span><span class='distancia'>a {p['distancia']} km</span>"
                f"<p class='bio'>{html.escape(str(p['bio']))}</p><ul class='intereses'>{intereses}</ul></section>"
                # Un formulario por acción, con id y acción como campos ocultos (como haría una app sin JS).
                f"<form id='f-like' method='post' action='/swipe'><input type='hidden' name='id' value='{p['id']}'>"
                "<input type='hidden' name='accion' value='like'><button type='submit' class='like'>❤</button></form>"
                f"<form id='f-pass' method='post' action='/swipe'><input type='hidden' name='id' value='{p['id']}'>"
                "<input type='hidden' name='accion' value='pass'><button type='submit' class='pass'>✕</button></form>"
            )

        def do_GET(self) -> None:  # noqa: N802
            if urlsplit(self.path).path == "/perfiles":
                return self._ok(self._tarjeta())
            self._ok(_html("404"), 404)

        def do_POST(self) -> None:  # noqa: N802
            n = int(self.headers.get("Content-Length", "0"))
            d = {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode()).items()}
            p = estado.pendiente()
            # Se rechaza (400) un swipe a un perfil que no es el visible: evita saltarse perfiles.
            if urlsplit(self.path).path != "/swipe" or p is None or d.get("id") != p["id"] or d.get("accion") not in ("like", "pass"):
                return self._ok(_html("<p class='error'>swipe inválido</p>"), 400)
            with estado.lock:
                estado.swipes.append((d["id"], d["accion"]))
            # Sólo hay match si fue like Y el perfil tiene match predefinido.
            extra = f"<p class='match'>¡Match con {html.escape(str(p['nombre']))}!</p>" if d["accion"] == "like" and p["match"] else ""
            self._ok(self._tarjeta(extra))

    return Handler


def iniciar(puerto: int = 0) -> tuple[ThreadingHTTPServer, EstadoApp]:
    estado = EstadoApp()
    srv = ThreadingHTTPServer(("127.0.0.1", puerto), crear_handler(estado))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, estado


if __name__ == "__main__":  # pragma: no cover
    ap = argparse.ArgumentParser()
    ap.add_argument("--puerto", type=int, default=8766)
    srv, _ = iniciar(ap.parse_args().puerto)
    print(f"App mock en http://127.0.0.1:{srv.server_address[1]}/perfiles")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        srv.shutdown()
