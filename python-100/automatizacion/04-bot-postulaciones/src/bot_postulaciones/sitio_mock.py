"""Sitio MOCK local que imita el flujo de un portal de empleo.

Se sirve en 127.0.0.1 con ``http.server`` (sin dependencias) y guarda en
memoria las postulaciones recibidas. Ejecutarlo a mano::

    python -m bot_postulaciones.sitio_mock --puerto 8765

Rutas:
- ``GET /ofertas?pagina=N`` listado paginado (3 ofertas por página)
- ``GET /oferta/<id>``       detalle
- ``GET /postular/<id>``     formulario
- ``POST /postular/<id>``    recibe la postulación
"""

from __future__ import annotations

import argparse
import html
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

# Ofertas ficticias (empresas y datos inventados).
OFERTAS_DEMO: list[dict[str, object]] = [
    {"id": "101", "titulo": "Desarrollador/a Python Backend", "empresa": "Acme Datos",
     "ubicacion": "Buenos Aires", "modalidad": "remoto", "salario": 3500,
     "descripcion": "Buscamos experiencia en Python, Django y PostgreSQL. Deseable Docker."},
    {"id": "102", "titulo": "Desarrollador/a Java Senior", "empresa": "Globex",
     "ubicacion": "Córdoba", "modalidad": "presencial", "salario": 4000,
     "descripcion": "Java 17, Spring Boot, microservicios."},
    {"id": "103", "titulo": "Data Engineer Python", "empresa": "Initech",
     "ubicacion": "Rosario", "modalidad": "hibrido", "salario": 2000,
     "descripcion": "Python, Airflow, SQL. Guardias rotativas de fin de semana."},
    {"id": "104", "titulo": "Python Developer (FastAPI)", "empresa": "Umbrella Soft",
     "ubicacion": "Buenos Aires", "modalidad": "hibrido", "salario": 3800,
     "descripcion": "Python, FastAPI, Docker, Kubernetes y testing con pytest."},
    {"id": "105", "titulo": "Frontend React", "empresa": "Hooli",
     "ubicacion": "Montevideo", "modalidad": "remoto", "salario": None,
     "descripcion": "React, TypeScript, CSS."},
    {"id": "106", "titulo": "Backend Python Trainee", "empresa": "Pied Piper",
     "ubicacion": "Mendoza", "modalidad": "presencial", "salario": 900,
     "descripcion": "Python básico y ganas de aprender."},
]
# 6 ofertas / 3 por página = 2 páginas: suficiente para probar la paginación.
POR_PAGINA = 3


@dataclass
class EstadoSitio:
    """Estado mutable del sitio (postulaciones recibidas)."""

    # Copia de cada oferta: los tests pueden mutar su estado sin afectar a otros tests.
    ofertas: list[dict[str, object]] = field(default_factory=lambda: [dict(o) for o in OFERTAS_DEMO])
    postulaciones: list[dict[str, str]] = field(default_factory=list)
    # ThreadingHTTPServer atiende cada request en un hilo: el lock protege la lista compartida.
    lock: threading.Lock = field(default_factory=threading.Lock)


def _pagina(titulo: str, cuerpo: str) -> bytes:
    return (f"<!doctype html><html lang='es'><head><meta charset='utf-8'><title>{html.escape(titulo)}</title>"
            f"</head><body><h1>{html.escape(titulo)}</h1>{cuerpo}</body></html>").encode("utf-8")


def crear_handler(estado: EstadoSitio) -> type[BaseHTTPRequestHandler]:
    """Fabrica una clase Handler con acceso al ``estado`` (closure)."""

    # Clase definida dentro de la función (closure) para capturar ``estado`` sin variables globales.
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:  # silencioso
            pass

        def _responder(self, codigo: int, contenido: bytes) -> None:
            self.send_response(codigo)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            # Content-Length en BYTES (ya codificados en UTF-8), no en caracteres.
            self.send_header("Content-Length", str(len(contenido)))
            self.end_headers()
            self.wfile.write(contenido)

        def _oferta(self, oid: str) -> dict[str, object] | None:
            return next((o for o in estado.ofertas if o["id"] == oid), None)

        def do_GET(self) -> None:  # noqa: N802 - nombre impuesto por http.server
            partes = urlsplit(self.path)
            ruta = partes.path.strip("/").split("/")
            if ruta[0] == "ofertas":
                n = int(parse_qs(partes.query).get("pagina", ["1"])[0])
                # Página n (base 1) → rebanada [(n−1)·3, n·3). Una página fuera de rango da lista vacía.
                trozo = estado.ofertas[(n - 1) * POR_PAGINA: n * POR_PAGINA]
                tarjetas = "".join(
                    # html.escape en todos los textos: el mock también evita XSS como lo haría un sitio real.
                    f"<article class='oferta' data-id='{o['id']}'><h2 class='titulo'>{html.escape(str(o['titulo']))}</h2>"
                    f"<span class='empresa'>{html.escape(str(o['empresa']))}</span>"
                    f"<span class='ubicacion'>{html.escape(str(o['ubicacion']))}</span>"
                    f"<span class='modalidad'>{o['modalidad']}</span>"
                    + (f"<span class='salario'>USD {o['salario']}</span>" if o["salario"] else "")
                    + f"<a class='ver' href='/oferta/{o['id']}'>Ver</a></article>"
                    for o in trozo
                )
                # Hay "Siguiente" mientras queden ofertas después de esta página.
                sig = f"<a class='siguiente' href='/ofertas?pagina={n + 1}'>Siguiente</a>" if n * POR_PAGINA < len(estado.ofertas) else ""
                return self._responder(200, _pagina(f"Ofertas - página {n}", f"<main>{tarjetas}</main>{sig}"))
            if ruta[0] == "oferta" and len(ruta) == 2 and (o := self._oferta(ruta[1])):
                ya = any(p["oferta"] == o["id"] for p in estado.postulaciones)
                accion = "<p class='ya-postulado'>Ya te postulaste</p>" if ya else f"<a class='postular' href='/postular/{o['id']}'>Postular</a>"
                return self._responder(200, _pagina(str(o["titulo"]), f"<div class='descripcion'>{html.escape(str(o['descripcion']))}</div>{accion}"))
            if ruta[0] == "postular" and len(ruta) == 2 and self._oferta(ruta[1]):
                form = (f"<form id='postulacion' method='post' action='/postular/{ruta[1]}'>"
                        "<input name='nombre'><input name='email' type='email'>"
                        "<textarea name='carta'></textarea><input type='hidden' name='token' value='demo'>"
                        "<button type='submit'>Enviar</button></form>")
                return self._responder(200, _pagina("Postulación", form))
            self._responder(404, _pagina("No encontrado", ""))

        def do_POST(self) -> None:  # noqa: N802
            ruta = urlsplit(self.path).path.strip("/").split("/")
            largo = int(self.headers.get("Content-Length", "0"))
            datos = {k: v[0] for k, v in parse_qs(self.rfile.read(largo).decode()).items()}
            if ruta[0] == "postular" and len(ruta) == 2 and self._oferta(ruta[1]):
                # Validación mínima del lado servidor: devuelve 400 y NO registra la postulación.
                if not datos.get("nombre") or "@" not in datos.get("email", ""):
                    return self._responder(400, _pagina("Datos inválidos", "<p class='error'>Faltan datos</p>"))
                # Se guardan todos los campos recibidos (incluido el token oculto) para inspeccionarlos en tests.
                with estado.lock:
                    estado.postulaciones.append({"oferta": ruta[1], **datos})
                return self._responder(200, _pagina("Listo", "<p class='confirmacion'>¡Postulación enviada!</p>"))
            self._responder(404, _pagina("No encontrado", ""))

    return Handler


def iniciar(puerto: int = 0) -> tuple[ThreadingHTTPServer, EstadoSitio]:
    """Inicia el servidor en un hilo; devuelve (servidor, estado). Puerto 0 = libre."""
    estado = EstadoSitio()
    srv = ThreadingHTTPServer(("127.0.0.1", puerto), crear_handler(estado))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, estado


if __name__ == "__main__":  # pragma: no cover
    ap = argparse.ArgumentParser()
    ap.add_argument("--puerto", type=int, default=8765)
    srv, _ = iniciar(ap.parse_args().puerto)
    print(f"Sitio mock en http://127.0.0.1:{srv.server_address[1]}/ofertas (Ctrl+C para salir)")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        srv.shutdown()
