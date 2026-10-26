"""API y vistas de los formularios dinámicos.

Creador (con token de dueño devuelto al crear):
  POST /api/formularios                         -> crea, devuelve slug + token_dueno
  GET  /api/formularios/{slug}/respuestas       -> lista (header X-Token-Dueno)
  GET  /api/formularios/{slug}/resumen          -> estadísticas por campo
  GET  /api/formularios/{slug}/export.csv       -> exportación CSV
  POST /api/formularios/{slug}/cerrar           -> deja de aceptar respuestas
Público:
  GET  /f/{slug}                                -> formulario HTML generado
  POST /f/{slug}                                -> envío desde el HTML (form-data)
  POST /api/formularios/{slug}/responder        -> envío JSON
  GET  /api/formularios/{slug}                  -> definición pública
"""
from __future__ import annotations

import csv
# html.escape: todo texto que escribe el creador del formulario se escapa
# antes de meterlo en el HTML generado.
import html
import io
import json
import os
import secrets
import sqlite3
import threading
# Counter y mean: para el resumen estadístico de respuestas.
from collections import Counter
from statistics import mean
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

from formularios.esquema import Campo, DefinicionFormulario, validar_respuesta

# La definición del formulario se guarda como JSON (validado por Pydantic al
# crear y al leer) y cada respuesta también: así un formulario puede tener
# cualquier cantidad y tipo de campos sin migrar el esquema SQL.
# `token` es el secreto del dueño; `abierto` permite cerrarlo.
ESQUEMA = """
CREATE TABLE IF NOT EXISTS formularios (
  slug TEXT PRIMARY KEY, definicion TEXT NOT NULL, token TEXT NOT NULL, abierto INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS respuestas (
  id INTEGER PRIMARY KEY, slug TEXT NOT NULL, datos TEXT NOT NULL, enviada TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
"""


def renderizar_html(slug: str, d: DefinicionFormulario, errores: dict[str, str] | None = None) -> str:
    """Genera el HTML del formulario. TODO texto del creador se escapa (anti-XSS)."""
    # Alias corto porque se usa en casi cada línea.
    e = html.escape
    partes = [f"<!doctype html><html lang='es'><meta charset='utf-8'><title>{e(d.titulo)}</title><body>",
              f"<h1>{e(d.titulo)}</h1><p>{e(d.descripcion)}</p><form method='post' action='/f/{e(slug)}'>"]
    # Un <fieldset> por campo, con la etiqueta como <legend> (accesible).
    # c.nombre se inserta sin escapar porque el modelo Campo ya lo restringe a
    # ^[a-z][a-z0-9_]*$ (no puede contener comillas ni "<").
    for c in d.campos:
        req = " required" if c.requerido else ""
        partes.append(f"<fieldset><legend>{e(c.etiqueta)}{' *' if c.requerido else ''}</legend>")
        # Párrafo = texto largo => <textarea>.
        if c.tipo == "parrafo":
            partes.append(f"<textarea name='{c.nombre}'{req}></textarea>")
        elif c.tipo in ("seleccion", "casillas"):
            # Selección única => radio; casillas (varias) => checkbox con mismo name.
            t = "radio" if c.tipo == "seleccion" else "checkbox"
            for o in c.opciones:
                # quote=True también escapa comillas: la opción va dentro de un atributo.
                # El "required" no se pone en radios/checkbox: lo valida el servidor.
                partes.append(f"<label><input type='{t}' name='{c.nombre}' value='{e(o, quote=True)}'> {e(o)}</label>")
        else:
            # Tipo de input HTML5 equivalente: el navegador ayuda con la validación,
            # aunque la validación que vale es la del servidor.
            t = {"texto": "text", "email": "email", "numero": "number", "fecha": "date"}[c.tipo]
            partes.append(f"<input type='{t}' name='{c.nombre}'{req}>")
        # Al re-mostrar el formulario con errores, el mensaje va bajo cada campo.
        if errores and c.nombre in errores:
            partes.append(f"<p class='error'>{e(errores[c.nombre])}</p>")
        partes.append("</fieldset>")
    partes.append("<button>Enviar</button></form></body></html>")
    # Se arma con una lista y join: más eficiente que concatenar strings.
    return "".join(partes)


def crear_app(ruta_db: str = ":memory:") -> FastAPI:
    app = FastAPI(title="Formularios dinámicos")
    # Una conexión compartida (FastAPI corre handlers sync en un pool de hilos)
    # con un lock para las escrituras.
    con = sqlite3.connect(ruta_db, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(ESQUEMA)
    lock = threading.Lock()

    # Busca el formulario y re-valida su definición JSON con Pydantic: así el
    # resto del código trabaja con objetos tipados en vez de dicts sueltos.
    def cargar(slug: str) -> tuple[DefinicionFormulario, sqlite3.Row]:
        f = con.execute("SELECT * FROM formularios WHERE slug = ?", (slug,)).fetchone()
        if f is None:
            raise HTTPException(404, "Formulario no encontrado")
        return DefinicionFormulario.model_validate_json(f["definicion"]), f

    # Sin cuentas de usuario: quien tiene el token de dueño administra el
    # formulario. Comparación en tiempo constante.
    def exigir_dueno(fila: sqlite3.Row, token: str) -> None:
        if not secrets.compare_digest(token, fila["token"]):
            raise HTTPException(403, "Token de dueño inválido")

    # Lógica compartida por el envío JSON y el HTML: chequear que esté abierto,
    # validar y, solo si no hay errores, insertar.
    def guardar(slug: str, campos: list[Campo], datos: dict[str, Any], fila: sqlite3.Row):
        if not fila["abierto"]:
            raise HTTPException(409, "El formulario está cerrado")
        limpio, errores = validar_respuesta(campos, datos)
        if not errores:
            with lock:
                # ensure_ascii=False guarda "azúcar" legible en vez de "az\u00facar".
                con.execute("INSERT INTO respuestas (slug, datos) VALUES (?, ?)", (slug, json.dumps(limpio, ensure_ascii=False)))
                con.commit()
        return limpio, errores

    def respuestas(slug: str) -> list[dict[str, Any]]:
        # Aplana cada respuesta: id, fecha y los campos respondidos.
        return [{"id": r["id"], "enviada": r["enviada"], **json.loads(r["datos"])}
                for r in con.execute("SELECT * FROM respuestas WHERE slug = ? ORDER BY id", (slug,))]

    @app.post("/api/formularios", status_code=201)
    def crear(d: DefinicionFormulario):
        # slug corto (público, va en la URL) y token largo (secreto del dueño).
        # 6 bytes = 2^48 combinaciones: suficiente para que no colisionen ni se
        # puedan enumerar formularios ajenos.
        slug, token = secrets.token_urlsafe(6), secrets.token_urlsafe(24)
        with lock:
            con.execute("INSERT INTO formularios (slug, definicion, token) VALUES (?, ?, ?)", (slug, d.model_dump_json(), token))
            con.commit()
        # El token se devuelve una sola vez: el creador debe guardarlo.
        return {"slug": slug, "token_dueno": token, "url_publica": f"/f/{slug}"}

    @app.get("/api/formularios/{slug}")
    def definicion(slug: str):
        d, f = cargar(slug)
        # Definición pública: no incluye el token de dueño.
        return {**d.model_dump(), "abierto": bool(f["abierto"])}

    @app.post("/api/formularios/{slug}/responder", status_code=201)
    def responder_json(slug: str, datos: dict[str, Any]):
        d, f = cargar(slug)
        limpio, errores = guardar(slug, d.campos, datos, f)
        if errores:
            # El detalle trae un error por campo, para que el cliente los muestre.
            raise HTTPException(422, {"errores": errores})
        return {"ok": True, "datos": limpio}

    @app.get("/f/{slug}", response_class=HTMLResponse)
    def ver_html(slug: str):
        d, _ = cargar(slug)
        return renderizar_html(slug, d)

    @app.post("/f/{slug}", response_class=HTMLResponse)
    async def responder_html(slug: str, request: Request):
        d, f = cargar(slug)
        # request.form() es async; por eso este handler es `async def`.
        form = await request.form()
        # Las casillas llegan repetidas con el mismo nombre -> getlist
        datos = {c.nombre: (form.getlist(c.nombre) if c.tipo == "casillas" else form.get(c.nombre)) for c in d.campos}
        _, errores = guardar(slug, d.campos, datos, f)
        if errores:
            # Se vuelve a mostrar el formulario con los mensajes de error.
            return HTMLResponse(renderizar_html(slug, d, errores), status_code=422)
        return "<p>¡Gracias! Tu respuesta fue registrada.</p>"

    @app.get("/api/formularios/{slug}/respuestas")
    def listar(slug: str, x_token_dueno: str = Header(default="")):
        _, f = cargar(slug)
        exigir_dueno(f, x_token_dueno)
        return respuestas(slug)

    @app.post("/api/formularios/{slug}/cerrar")
    def cerrar(slug: str, x_token_dueno: str = Header(default="")):
        _, f = cargar(slug)
        exigir_dueno(f, x_token_dueno)
        with lock:
            con.execute("UPDATE formularios SET abierto = 0 WHERE slug = ?", (slug,))
            con.commit()
        return {"abierto": False}

    @app.get("/api/formularios/{slug}/resumen")
    def resumen(slug: str, x_token_dueno: str = Header(default="")):
        """Estadísticas: conteo por opción, promedio/mín/máx de números, cantidad de textos."""
        d, f = cargar(slug)
        exigir_dueno(f, x_token_dueno)
        rs = respuestas(slug)
        # Un resumen por campo según su tipo.
        salida: dict[str, Any] = {"total": len(rs), "campos": {}}
        for c in d.campos:
            # Solo las respuestas que completaron ese campo (los opcionales pueden faltar).
            valores = [r[c.nombre] for r in rs if c.nombre in r]
            if c.tipo == "seleccion":
                # Se recorren las opciones definidas (no los valores) para que las que
                # nadie eligió aparezcan con 0.
                info: dict[str, Any] = {o: Counter(valores).get(o, 0) for o in c.opciones}
            elif c.tipo == "casillas":
                # Casillas: cada respuesta es una lista; se cuentan todas las marcadas.
                cnt = Counter(x for v in valores for x in v)
                info = {o: cnt.get(o, 0) for o in c.opciones}
            elif c.tipo == "numero" and valores:
                # `and valores`: mean() de una lista vacía lanza error; sin números cae al else.
                info = {"promedio": round(mean(valores), 2), "minimo": min(valores), "maximo": max(valores)}
            else:
                # Texto, email, fecha: solo se informa cuántos lo respondieron.
                info = {"respondidas": len(valores)}
            salida["campos"][c.nombre] = info
        return salida

    @app.get("/api/formularios/{slug}/export.csv", response_class=PlainTextResponse)
    def exportar(slug: str, x_token_dueno: str = Header(default="")):
        d, f = cargar(slug)
        exigir_dueno(f, x_token_dueno)
        buf = io.StringIO()
        # Columnas fijas + una por campo, en el orden del formulario.
        # extrasaction="ignore": si hay datos de campos viejos, no rompe.
        cols = ["id", "enviada"] + [c.nombre for c in d.campos]
        w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in respuestas(slug):
            # Casillas (listas) => "leche; canela" en una sola celda.
            fila = {k: ("; ".join(v) if isinstance(v, list) else v) for k, v in r.items()}
            # Evita "inyección de fórmulas" al abrir el CSV en Excel
            # Excel interpreta como fórmula lo que empieza con = + - @; anteponer un
            # apóstrofo lo fuerza a texto. v[:1] no falla con strings vacíos.
            fila = {k: ("'" + v if isinstance(v, str) and v[:1] in "=+-@" else v) for k, v in fila.items()}
            w.writerow(fila)
        return PlainTextResponse(buf.getvalue(), media_type="text/csv")

    return app


app = crear_app(os.environ.get("FORMULARIOS_DB", ":memory:"))
