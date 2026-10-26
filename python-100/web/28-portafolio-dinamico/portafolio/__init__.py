"""Portafolio personal dinámico (proyecto 28).

- Sitio público: lista de proyectos (filtrable por etiqueta), detalle y contacto.
- API JSON pública: /api/proyectos (para consumir desde otro front).
- Panel /admin: login de un único administrador (hash en variable de entorno),
  alta/edición/borrado de proyectos y lectura de mensajes. CSRF en todos los POST.
"""
from __future__ import annotations

import os
import re
import secrets
import sqlite3
# unicodedata: para quitar acentos al generar slugs ("Ñandú" -> "nandu").
import unicodedata
from functools import wraps
from typing import Any

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)
# Solo se verifica: el hash del admin se genera fuera de la app y llega por
# variable de entorno, así la contraseña nunca está en el código ni en la base.
from werkzeug.security import check_password_hash

# - proyectos.slug UNIQUE: es el identificador que aparece en la URL.
# - etiquetas se guardan como texto "python,flask" (normalizado): para un
#   portafolio de decenas de proyectos no se justifica una tabla aparte.
# - destacado/orden controlan qué se muestra primero.
# - mensajes: lo que llega por el formulario de contacto.
ESQUEMA = """
CREATE TABLE IF NOT EXISTS proyectos (
  id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT UNIQUE NOT NULL, titulo TEXT NOT NULL,
  resumen TEXT NOT NULL, descripcion TEXT NOT NULL DEFAULT '', url_repo TEXT NOT NULL DEFAULT '',
  etiquetas TEXT NOT NULL DEFAULT '', destacado INTEGER NOT NULL DEFAULT 0, orden INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS mensajes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL, email TEXT NOT NULL,
  texto TEXT NOT NULL, recibido TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
"""


def slugificar(texto: str) -> str:
    """'Mi Proyecto Ñandú!' -> 'mi-proyecto-nandu' (quita acentos y símbolos)."""
    # NFKD separa "ñ" en "n" + tilde combinante; al codificar a ASCII con
    # "ignore" se descartan las tildes y queda la letra base.
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    # Todo lo que no sea letra/dígito se vuelve un guion (los grupos se
    # colapsan en uno solo). Si queda vacío (título "!!!") se usa "proyecto".
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-") or "proyecto"


def etiquetas_lista(texto: str) -> list[str]:
    """'Python, Flask ,  SQL' -> ['python', 'flask', 'sql'] (sin duplicados, en orden)."""
    # Lista (y no set) para conservar el orden en que se escribieron.
    vistas: list[str] = []
    for e in (x.strip().lower() for x in texto.split(",")):
        # Se descartan vacías (",," o coma final) y repetidas ("python" dos veces).
        if e and e not in vistas:
            vistas.append(e)
    return vistas


# Patrón "application factory": cada llamada crea una app independiente,
# lo que permite que cada test use su propia base temporal.
def crear_app(config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(
        # Clave de firma de cookies desde el entorno (o aleatoria en desarrollo).
        SECRET_KEY=os.environ.get("PORTAFOLIO_SECRET_KEY") or secrets.token_hex(32),
        DATABASE=os.environ.get("PORTAFOLIO_DB", "portafolio.db"),
        # Hash generado con: python -c "from werkzeug.security import generate_password_hash as g;print(g('clave'))"
        ADMIN_USUARIO=os.environ.get("PORTAFOLIO_ADMIN", "admin"),
        # Vacío por defecto => el panel admin queda deshabilitado (más seguro que
        # venir con una contraseña por defecto).
        ADMIN_HASH=os.environ.get("PORTAFOLIO_ADMIN_HASH", ""),
        # HttpOnly: JavaScript no puede leer la cookie (mitiga robo por XSS).
        # SameSite=Lax: el navegador no la manda en POST desde otros sitios.
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
    )
    # La config de los tests pisa la del entorno.
    if config:
        app.config.update(config)

    def db() -> sqlite3.Connection:
        # Una conexión por petición, guardada en `g` y cerrada en teardown.
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
        return g.db

    @app.teardown_appcontext
    # Se ejecuta al terminar cada petición, haya error o no.
    def _cerrar(_e):
        c = g.pop("db", None)
        if c:
            c.close()

    # Crea las tablas al iniciar (idempotente por IF NOT EXISTS).
    with app.app_context():
        db().executescript(ESQUEMA)

    # ---------- CSRF ----------
    def csrf_token() -> str:
        # Token CSRF por sesión, disponible en las plantillas como csrf_token().
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(32)
        return session["csrf"]
    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def _csrf():
        if request.method == "POST":
            # Si la sesión no tiene token se compara contra "\0", que nunca coincide
            # con un token real: sin sesión previa, ningún POST pasa.
            if not secrets.compare_digest(request.form.get("csrf_token", ""), session.get("csrf", "") or "\0"):
                abort(400, description="CSRF inválido")

    # Decorador para las vistas del panel: sin sesión de admin => al login.
    def admin_requerido(f):
        @wraps(f)
        def env(*a, **kw):
            if not session.get("admin"):
                return redirect(url_for("login"))
            return f(*a, **kw)
        return env

    # Convierte la fila de SQLite al formato de la API: etiquetas como lista
    # y destacado como bool.
    def fila_a_dict(f: sqlite3.Row) -> dict[str, Any]:
        d = dict(f)
        d["etiquetas"] = etiquetas_lista(d["etiquetas"])
        d["destacado"] = bool(d["destacado"])
        return d

    def listar(etiqueta: str | None = None) -> list[dict[str, Any]]:
        # Orden: destacados primero, luego por "orden" manual y, a igualdad, por id.
        filas = db().execute("SELECT * FROM proyectos ORDER BY destacado DESC, orden, id").fetchall()
        proys = [fila_a_dict(f) for f in filas]
        # El filtro por etiqueta se hace en Python: compara contra la lista ya
        # separada, así "sql" no matchea por error a "postgresql".
        return [p for p in proys if etiqueta in p["etiquetas"]] if etiqueta else proys

    # ---------- Público ----------
    @app.get("/")
    def inicio():
        etiqueta = request.args.get("etiqueta")
        # Conjunto de todas las etiquetas usadas, para armar los botones de filtro.
        todas = sorted({e for p in listar() for e in p["etiquetas"]})
        return render_template("inicio.html", proyectos=listar(etiqueta), etiquetas=todas, activa=etiqueta)

    # Detalle de un proyecto por su slug; inexistente => 404.
    @app.get("/proyecto/<slug>")
    def detalle(slug: str):
        f = db().execute("SELECT * FROM proyectos WHERE slug = ?", (slug,)).fetchone()
        if f is None:
            abort(404)
        return render_template("detalle.html", p=fila_a_dict(f))

    # Misma información en JSON, para consumirla desde otro frontend.
    @app.get("/api/proyectos")
    def api_proyectos():
        return jsonify(listar(request.args.get("etiqueta")))

    @app.route("/contacto", methods=["GET", "POST"])
    def contacto():
        if request.method == "POST":
            # Honeypot: campo oculto que un humano no completa; si viene lleno es un bot
            # Se responde como si todo hubiera salido bien para no darle pistas al bot.
            if request.form.get("sitio_web"):
                return redirect(url_for("inicio"))
            # Se recortan los largos para que nadie llene la base con textos gigantes.
            nombre = request.form.get("nombre", "").strip()[:100]
            email = request.form.get("email", "").strip()[:200]
            texto = request.form.get("texto", "").strip()[:5000]
            # Regex de email deliberadamente simple: algo@algo.algo, sin espacios.
            if not nombre or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email) or len(texto) < 10:
                flash("Revisá los datos: nombre, email válido y un mensaje de al menos 10 caracteres.")
                return render_template("contacto.html"), 400
            db().execute("INSERT INTO mensajes (nombre, email, texto) VALUES (?, ?, ?)", (nombre, email, texto))
            db().commit()
            flash("¡Gracias! Te respondo pronto.")
            return redirect(url_for("inicio"))
        return render_template("contacto.html")

    # ---------- Admin ----------
    @app.route("/admin/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            # Se compara usuario y clave siempre (sin cortar antes) y se responde el
            # mismo error genérico, para no revelar cuál de los dos falló.
            ok_usuario = secrets.compare_digest(request.form.get("usuario", ""), app.config["ADMIN_USUARIO"])
            h = app.config["ADMIN_HASH"]
            # Si no hay hash configurado, el panel queda deshabilitado
            if h and ok_usuario and check_password_hash(h, request.form.get("clave", "")):
                # Sesión nueva al loguearse: previene fijación de sesión.
                session.clear()
                session["admin"] = True
                return redirect(url_for("admin"))
            flash("Credenciales inválidas.")
            return render_template("login.html"), 401
        return render_template("login.html")

    # Logout por POST (con CSRF) para que un <img src=...> ajeno no lo dispare.
    @app.post("/admin/logout")
    def logout():
        session.clear()
        return redirect(url_for("inicio"))

    @app.get("/admin")
    @admin_requerido
    def admin():
        msgs = db().execute("SELECT * FROM mensajes ORDER BY id DESC").fetchall()
        return render_template("admin.html", proyectos=listar(), mensajes=msgs)

    # Lee y valida el formulario de proyecto (compartido por alta y edición).
    def datos_form() -> dict[str, Any]:
        titulo = request.form.get("titulo", "").strip()
        resumen = request.form.get("resumen", "").strip()
        url_repo = request.form.get("url_repo", "").strip()
        if not titulo or not resumen:
            abort(400, description="Título y resumen son obligatorios")
        # Evita guardar enlaces javascript: que se ejecutarían al hacer clic.
        if url_repo and not url_repo.startswith(("https://", "http://")):
            abort(400, description="La URL del repositorio debe ser http(s)")
        return {"titulo": titulo, "resumen": resumen, "descripcion": request.form.get("descripcion", "").strip(),
                "url_repo": url_repo, "etiquetas": ",".join(etiquetas_lista(request.form.get("etiquetas", ""))),
                "destacado": 1 if request.form.get("destacado") else 0,
                # `or 0` cubre el campo enviado vacío ("").
                "orden": int(request.form.get("orden", "0") or 0)}

    @app.post("/admin/proyectos")
    @admin_requerido
    def crear_proyecto():
        d = datos_form()
        # Si "api-de-tareas" existe se prueba "api-de-tareas-2", "-3", etc.
        base = slug = slugificar(d["titulo"])
        n = 2
        # Si el slug existe se le agrega un sufijo numérico
        while db().execute("SELECT 1 FROM proyectos WHERE slug = ?", (slug,)).fetchone():
            slug, n = f"{base}-{n}", n + 1
        # Parámetros con nombre (:slug, :titulo...) tomados del diccionario.
        db().execute("INSERT INTO proyectos (slug, titulo, resumen, descripcion, url_repo, etiquetas, destacado, orden)"
                     " VALUES (:slug, :titulo, :resumen, :descripcion, :url_repo, :etiquetas, :destacado, :orden)",
                     {**d, "slug": slug})
        db().commit()
        return redirect(url_for("detalle", slug=slug))

    @app.post("/admin/proyectos/<int:pid>")
    @admin_requerido
    def editar_proyecto(pid: int):
        d = datos_form()
        cur = db().execute("UPDATE proyectos SET titulo=:titulo, resumen=:resumen, descripcion=:descripcion,"
                           " url_repo=:url_repo, etiquetas=:etiquetas, destacado=:destacado, orden=:orden WHERE id=:id",
                           {**d, "id": pid})
        db().commit()
        # Ninguna fila actualizada => el id no existía.
        if cur.rowcount == 0:
            abort(404)
        return redirect(url_for("admin"))

    @app.post("/admin/proyectos/<int:pid>/borrar")
    @admin_requerido
    # Borrado físico: un proyecto del portafolio no necesita historial.
    def borrar_proyecto(pid: int):
        db().execute("DELETE FROM proyectos WHERE id = ?", (pid,))
        db().commit()
        return redirect(url_for("admin"))

    return app
