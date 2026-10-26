"""API del acortador.

POST   /api/enlaces              -> crea un enlace (alias opcional, vencimiento opcional)
GET    /{codigo}                 -> redirige (307) y registra el clic
GET    /api/enlaces/{codigo}     -> estadísticas (total, por día, por referer)
DELETE /api/enlaces/{codigo}     -> borra, requiere el header X-Token-Borrado
"""
from __future__ import annotations

import os
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Callable
# urlsplit: se usa para quedarse solo con el host del referer.
from urllib.parse import urlsplit

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from acortador.codigos import codigo_aleatorio, validar_alias, validar_url

# - enlaces.codigo es la PK: garantiza unicidad de códigos y alias.
# - token_borrado: secreto que solo conoce quien creó el enlace.
# - clics: ON DELETE CASCADE borra las estadísticas junto con el enlace
#   (requiere PRAGMA foreign_keys = ON, que se activa más abajo).
# - El índice por código acelera los COUNT/GROUP BY de las estadísticas.
ESQUEMA = """
CREATE TABLE IF NOT EXISTS enlaces (
  codigo TEXT PRIMARY KEY, url TEXT NOT NULL, token_borrado TEXT NOT NULL,
  creado TEXT NOT NULL, vence TEXT);
CREATE TABLE IF NOT EXISTS clics (
  codigo TEXT NOT NULL REFERENCES enlaces(codigo) ON DELETE CASCADE,
  momento TEXT NOT NULL, referer_host TEXT);
CREATE INDEX IF NOT EXISTS idx_clics_codigo ON clics(codigo);
"""


class NuevoEnlace(BaseModel):
    # 2048: límite práctico de URLs que aceptan navegadores y servidores.
    url: str = Field(max_length=2048)
    alias: str | None = None
    # Opcional: entre 1 día y 10 años; None = no vence nunca.
    dias_validez: int | None = Field(default=None, ge=1, le=3650)


def crear_app(ruta_db: str = ":memory:", reloj: Callable[[], datetime] | None = None,
              base_url: str = "http://localhost:8000") -> FastAPI:
    """Fábrica de la app. `reloj` es inyectable para testear vencimientos."""
    app = FastAPI(title="Acortador de URLs")
    con = sqlite3.connect(ruta_db, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(ESQUEMA)
    lock = threading.Lock()
    # Reloj inyectable: los tests "adelantan" el tiempo sin dormir.
    ahora = reloj or (lambda: datetime.now(timezone.utc))

    # Helper común: todas las rutas que reciben un código responden 404 igual.
    def buscar(codigo: str) -> sqlite3.Row:
        fila = con.execute("SELECT * FROM enlaces WHERE codigo = ?", (codigo,)).fetchone()
        if fila is None:
            raise HTTPException(404, "Enlace no encontrado")
        return fila

    # Chequeo de vida para balanceadores/monitoreo. Va ANTES de "/{codigo}"
    # porque FastAPI evalúa las rutas en orden de registro.
    @app.get("/health")
    def health():
        return {"ok": True}

    @app.post("/api/enlaces", status_code=201)
    def crear(datos: NuevoEnlace):
        try:
            # La validación vive en codigos.py (testeable sin HTTP); acá se traduce
            # ValueError -> 422 para el cliente.
            url = validar_url(datos.url)
            alias = validar_alias(datos.alias) if datos.alias else None
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        # El vencimiento se guarda como fecha absoluta ISO (con zona horaria UTC).
        vence = (ahora() + timedelta(days=datos.dias_validez)).isoformat() if datos.dias_validez else None
        token = secrets.token_urlsafe(24)  # se muestra una sola vez al creador
        with lock:
            # Con alias: si ya existe, 409 Conflict (no se pisa el enlace de otro).
            if alias:
                codigo = alias
                if con.execute("SELECT 1 FROM enlaces WHERE codigo = ?", (codigo,)).fetchone():
                    raise HTTPException(409, "Ese alias ya está en uso")
            else:
                # Reintenta ante la (improbable) colisión de códigos aleatorios
                # Con 62^7 combinaciones una colisión es rarísima, pero se verifica igual:
                # el costo es una consulta y elimina un error imposible de reproducir.
                while True:
                    codigo = codigo_aleatorio()
                    if not con.execute("SELECT 1 FROM enlaces WHERE codigo = ?", (codigo,)).fetchone():
                        break
            # El chequeo y el INSERT ocurren dentro del mismo lock: no hay carrera.
            con.execute("INSERT INTO enlaces VALUES (?, ?, ?, ?, ?)",
                        (codigo, url, token, ahora().isoformat(), vence))
            con.commit()
        # El token de borrado se devuelve UNA sola vez; no hay endpoint para recuperarlo.
        return {"codigo": codigo, "corto": f"{base_url}/{codigo}", "url": url,
                "vence": vence, "token_borrado": token}

    @app.get("/api/enlaces/{codigo}")
    def estadisticas(codigo: str):
        e = buscar(codigo)
        # Las estadísticas se calculan en SQL (agregaciones), no trayendo todo a Python.
        total = con.execute("SELECT COUNT(*) FROM clics WHERE codigo = ?", (codigo,)).fetchone()[0]
        por_dia = {f[0]: f[1] for f in con.execute(
            # substr(1, 10) de un timestamp ISO = "AAAA-MM-DD": agrupa por día UTC.
            "SELECT substr(momento, 1, 10) d, COUNT(*) FROM clics WHERE codigo = ? GROUP BY d ORDER BY d", (codigo,))}
        # Sin referer (acceso directo, app, o el navegador lo ocultó) => "directo".
        por_ref = {(f[0] or "directo"): f[1] for f in con.execute(
            "SELECT referer_host, COUNT(*) FROM clics WHERE codigo = ? GROUP BY referer_host", (codigo,))}
        return {"codigo": codigo, "url": e["url"], "creado": e["creado"], "vence": e["vence"],
                "clics": total, "por_dia": por_dia, "por_referer": por_ref}

    @app.delete("/api/enlaces/{codigo}", status_code=204)
    def borrar(codigo: str, x_token_borrado: str = Header(default="")):
        e = buscar(codigo)
        # 403 si el token no coincide (el enlace existe pero no sos el dueño).
        if not secrets.compare_digest(x_token_borrado, e["token_borrado"]):
            raise HTTPException(403, "Token de borrado incorrecto")
        with lock:
            # El CASCADE también borra sus clics.
            con.execute("DELETE FROM enlaces WHERE codigo = ?", (codigo,))
            con.commit()

    # Ruta "atrapa-todo": se registra al final para no tapar /api y /health.
    @app.get("/{codigo}")
    def redirigir(codigo: str, request: Request):
        e = buscar(codigo)
        # 410 Gone (y no 404): el enlace existió pero ya no está disponible.
        if e["vence"] and datetime.fromisoformat(e["vence"]) < ahora():
            raise HTTPException(410, "El enlace venció")
        # Solo se guarda el host del referer (no la URL completa) por privacidad
        ref = request.headers.get("referer")
        ref_host = urlsplit(ref).hostname if ref else None
        with lock:
            con.execute("INSERT INTO clics VALUES (?, ?, ?)", (codigo, ahora().isoformat(), ref_host))
            con.commit()
        # 307: redirección temporal, así cada visita pasa por acá y se cuenta
        return RedirectResponse(e["url"], status_code=307)

    return app


# base_url configurable para generar los enlaces cortos con el dominio real.
app = crear_app(os.environ.get("ACORTADOR_DB", ":memory:"),
                base_url=os.environ.get("ACORTADOR_BASE_URL", "http://localhost:8000"))
