"""Blog con autenticación (proyecto 22).

Características de seguridad:
- Contraseñas con hash `scrypt` de Werkzeug (sal aleatoria por usuario).
- Token CSRF por sesión, verificado en TODOS los POST.
- Cookies de sesión HttpOnly y SameSite=Lax.
- Solo el autor puede editar/borrar sus artículos.
- Jinja2 escapa el HTML automáticamente (previene XSS).
"""
from __future__ import annotations

import os
# secrets (y no random): genera valores criptográficamente seguros para tokens.
import secrets
import sqlite3
from functools import wraps
from typing import Any, Callable

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
# Werkzeug ya viene con Flask: generate_password_hash usa scrypt con sal
# aleatoria, y el hash resultante incluye método+sal ("scrypt:...$sal$hash").
from werkzeug.security import check_password_hash, generate_password_hash

# Dos tablas: usuarios (nombre único) y artículos con FK al autor.
# UNIQUE en nombre hace que la base misma impida duplicados, incluso con
# dos registros simultáneos (el chequeo en Python solo sería una carrera).
ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT UNIQUE NOT NULL,
    hash_clave TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS articulos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    autor_id INTEGER NOT NULL REFERENCES usuarios(id),
    titulo TEXT NOT NULL,
    cuerpo TEXT NOT NULL,
    creado TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def crear_app(config: dict[str, Any] | None = None) -> Flask:
    """Fábrica de la aplicación Flask (patrón application factory)."""
    # __name__ le indica a Flask dónde buscar templates/ (junto a este paquete).
    app = Flask(__name__)
    app.config.update(
        # La clave secreta firma la cookie de sesión: se toma del entorno;
        # si no hay, se genera una aleatoria (las sesiones no sobreviven reinicios).
        SECRET_KEY=os.environ.get("BLOG_SECRET_KEY") or secrets.token_hex(32),
        DATABASE=os.environ.get("BLOG_DB", "blog.db"),
        # HttpOnly: JavaScript no puede leer la cookie (mitiga robo de sesión por XSS).
        SESSION_COOKIE_HTTPONLY=True,
        # Lax: el navegador no manda la cookie en POST desde otros sitios
        # (primera línea de defensa contra CSRF; el token es la segunda).
        SESSION_COOKIE_SAMESITE="Lax",
    )
    # La config explícita (tests) pisa a la del entorno.
    if config:
        app.config.update(config)

    # ---------------- Base de datos ----------------
    def db() -> sqlite3.Connection:
        """Conexión SQLite por petición, guardada en `g`."""
        # `g` vive lo que dura una petición: una sola conexión por request,
        # reutilizada por todas las llamadas a db() de esa petición.
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
            # SQLite trae las FK desactivadas por defecto: hay que activarlas por conexión.
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    @app.teardown_appcontext
    def cerrar_db(_exc: BaseException | None) -> None:
        """Cierra la conexión al terminar cada petición."""
        # pop con default: si la petición nunca tocó la base, no hay nada que cerrar.
        con = g.pop("db", None)
        if con is not None:
            con.close()

    # El esquema se crea al construir la app (fuera de una petición se necesita
    # un app_context para poder usar `g`).
    with app.app_context():
        db().executescript(ESQUEMA)

    # ---------------- CSRF ----------------
    def token_csrf() -> str:
        """Devuelve (y crea si hace falta) el token CSRF de la sesión."""
        # Un token por sesión (no por formulario): más simple y suficiente cuando la
        # sesión está firmada y la cookie es HttpOnly.
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(32)
        return session["csrf"]

    # Disponible en las plantillas como {{ csrf_token() }}
    app.jinja_env.globals["csrf_token"] = token_csrf

    @app.before_request
    def verificar_csrf() -> None:
        """Rechaza con 400 cualquier POST sin el token correcto."""
        # Solo se protegen los métodos que cambian estado; GET debe ser seguro.
        if request.method == "POST":
            # El token viaja en un campo oculto del formulario; el atacante de otro sitio
            # no puede leerlo (same-origin policy), así que no puede falsificar el POST.
            enviado = request.form.get("csrf_token", "")
            esperado = session.get("csrf", "")
            # compare_digest: comparación en tiempo constante
            # "not esperado": sin sesión previa no hay token válido posible.
            if not esperado or not secrets.compare_digest(enviado, esperado):
                abort(400, description="Token CSRF inválido")

    # ---------------- Autenticación ----------------
    @app.before_request
    def cargar_usuario() -> None:
        """Carga el usuario logueado (si lo hay) en g.usuario."""
        # La sesión solo guarda el id; los datos se releen de la base en cada pedido,
        # así un usuario borrado deja de estar logueado.
        uid = session.get("uid")
        g.usuario = db().execute("SELECT id, nombre FROM usuarios WHERE id = ?", (uid,)).fetchone() if uid else None

    # @wraps conserva el nombre de la vista: Flask usa ese nombre para url_for.
    def login_requerido(vista: Callable) -> Callable:
        """Decorador: redirige al login si no hay sesión."""
        @wraps(vista)
        def envoltura(*a: Any, **kw: Any):
            if g.usuario is None:
                # Se recuerda adónde quería ir el usuario para volver después del login.
                return redirect(url_for("login", siguiente=request.path))
            return vista(*a, **kw)
        return envoltura

    @app.route("/registro", methods=["GET", "POST"])
    def registro():
        if request.method == "POST":
            nombre = request.form.get("nombre", "").strip()
            clave = request.form.get("clave", "")
            error = None
            # Validación del lado del servidor: el HTML puede saltearse con curl.
            if not (3 <= len(nombre) <= 30) or not nombre.isalnum():
                error = "El usuario debe tener 3-30 caracteres alfanuméricos."
            # Largo mínimo 8 (recomendación NIST); no se exigen símbolos raros.
            elif len(clave) < 8:
                error = "La contraseña debe tener al menos 8 caracteres."
            if error is None:
                try:
                    db().execute("INSERT INTO usuarios (nombre, hash_clave) VALUES (?, ?)",
                                 (nombre, generate_password_hash(clave)))
                    db().commit()
                # La restricción UNIQUE de la base detecta el duplicado.
                except sqlite3.IntegrityError:
                    error = "Ese usuario ya existe."
                # else del try: solo se ejecuta si el INSERT funcionó.
                else:
                    flash("Cuenta creada. Iniciá sesión.")
                    return redirect(url_for("login"))
            flash(error)
            # 400 con el formulario de nuevo y el mensaje de error (vía flash).
            return render_template("auth.html", titulo="Registro"), 400
        return render_template("auth.html", titulo="Registro")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            fila = db().execute("SELECT * FROM usuarios WHERE nombre = ?",
                                (request.form.get("nombre", ""),)).fetchone()
            # check_password_hash recalcula el hash con la sal guardada y compara en
            # tiempo constante. Si el usuario no existe, `fila` es None y se rechaza igual.
            if fila and check_password_hash(fila["hash_clave"], request.form.get("clave", "")):
                # Se limpia la sesión para evitar fijación de sesión y se
                # regenera el token CSRF.
                session.clear()
                session["uid"] = fila["id"]
                siguiente = request.args.get("siguiente", "")
                # Solo se permiten redirecciones internas (evita open redirect)
                # "//sitio.com" es una URL relativa al protocolo: el navegador iría a OTRO
                # dominio, por eso también se rechaza.
                if not siguiente.startswith("/") or siguiente.startswith("//"):
                    siguiente = url_for("inicio")
                return redirect(siguiente)
            # Mensaje genérico: no revela si el usuario existe
            flash("Usuario o contraseña incorrectos.")
            # 401 Unauthorized: credenciales inválidas.
            return render_template("auth.html", titulo="Iniciar sesión"), 401
        return render_template("auth.html", titulo="Iniciar sesión")

    # Logout por POST (con CSRF): un <img src="/logout"> de otro sitio no puede
    # desloguear al usuario.
    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("inicio"))

    # ---------------- Artículos ----------------
    def articulo_o_404(aid: int, verificar_autor: bool = False) -> sqlite3.Row:
        """Busca un artículo; opcionalmente exige que el usuario sea el autor."""
        # JOIN para traer el nombre del autor junto al artículo en una sola consulta.
        art = db().execute(
            "SELECT a.*, u.nombre AS autor FROM articulos a JOIN usuarios u ON u.id = a.autor_id WHERE a.id = ?",
            (aid,)).fetchone()
        if art is None:
            # Primero 404 (no existe) y recién después 403 (existe pero no es tuyo).
            abort(404)
        if verificar_autor and (g.usuario is None or art["autor_id"] != g.usuario["id"]):
            # 403 Forbidden: logueado pero sin permiso sobre este recurso.
            abort(403)
        return art

    @app.get("/")
    def inicio():
        arts = db().execute(
            "SELECT a.*, u.nombre AS autor FROM articulos a JOIN usuarios u ON u.id = a.autor_id"
            # Más nuevos primero (id autoincremental ~ orden de creación).
            " ORDER BY a.id DESC").fetchall()
        return render_template("inicio.html", articulos=arts)

    @app.get("/articulo/<int:aid>")
    def ver(aid: int):
        return render_template("articulo.html", art=articulo_o_404(aid))

    # El orden de decoradores importa: route registra la vista ya envuelta por
    # login_requerido (los decoradores se aplican de abajo hacia arriba).
    @app.route("/nuevo", methods=["GET", "POST"])
    @login_requerido
    def nuevo():
        if request.method == "POST":
            titulo = request.form.get("titulo", "").strip()
            cuerpo = request.form.get("cuerpo", "").strip()
            # strip() antes: un título de solo espacios cuenta como vacío.
            if not titulo or not cuerpo:
                flash("Título y cuerpo son obligatorios.")
                return render_template("editar.html", art=None), 400
            cur = db().execute("INSERT INTO articulos (autor_id, titulo, cuerpo) VALUES (?, ?, ?)",
                               (g.usuario["id"], titulo, cuerpo))
            db().commit()
            # Patrón Post/Redirect/Get: recargar la página no reenvía el formulario.
            return redirect(url_for("ver", aid=cur.lastrowid))
        return render_template("editar.html", art=None)

    @app.route("/articulo/<int:aid>/editar", methods=["GET", "POST"])
    @login_requerido
    def editar(aid: int):
        # El permiso se verifica tanto en GET (ver el form) como en POST (guardar).
        art = articulo_o_404(aid, verificar_autor=True)
        if request.method == "POST":
            titulo = request.form.get("titulo", "").strip()
            cuerpo = request.form.get("cuerpo", "").strip()
            if not titulo or not cuerpo:
                flash("Título y cuerpo son obligatorios.")
                return render_template("editar.html", art=art), 400
            db().execute("UPDATE articulos SET titulo = ?, cuerpo = ? WHERE id = ?", (titulo, cuerpo, aid))
            db().commit()
            return redirect(url_for("ver", aid=aid))
        return render_template("editar.html", art=art)

    @app.post("/articulo/<int:aid>/borrar")
    @login_requerido
    def borrar(aid: int):
        # Borrar también exige ser el autor (si no, abort 403 antes del DELETE).
        articulo_o_404(aid, verificar_autor=True)
        db().execute("DELETE FROM articulos WHERE id = ?", (aid,))
        db().commit()
        return redirect(url_for("inicio"))

    return app
