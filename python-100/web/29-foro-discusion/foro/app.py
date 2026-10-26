"""API del foro.

Auth:     POST /registro, POST /login  -> token Bearer (vence en 7 días)
Hilos:    GET /hilos?orden=nuevos|top|populares, POST /hilos, GET /hilos/{id} (con árbol de respuestas)
Respuestas: POST /hilos/{id}/respuestas {texto, padre_id?}
Votos:    POST /votos {tipo: hilo|respuesta, id, valor: 1|0|-1}  (un voto por usuario; 0 lo quita)
Borrado:  DELETE /hilos/{id}, DELETE /respuestas/{id}  (solo el autor; borrado lógico)
"""
from __future__ import annotations

import os
import re
import sqlite3
import threading
import time
from typing import Any, Callable

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

# Ranking y seguridad están en módulos aparte: son funciones puras, fáciles
# de testear sin levantar la API.
from foro.ranking import puntaje_hot
from foro.seguridad import hashear_clave, huella_token, nuevo_token, verificar_clave

# 7 días en segundos. Los tiempos se manejan como epoch (float) para poder
# compararlos directo en SQL.
DURACION_TOKEN = 7 * 24 * 3600

# - tokens: se guarda la HUELLA (SHA-256) del token, nunca el token en sí.
# - hilos/respuestas: `borrado` para borrado lógico (no se pierde el árbol).
# - respuestas.padre_id NULL = respuesta directa al hilo; si no, a otra respuesta.
# - votos: PK (usuario, tipo, objeto) => la base garantiza 1 voto por persona.
ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (id INTEGER PRIMARY KEY, nombre TEXT UNIQUE NOT NULL, hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tokens (huella TEXT PRIMARY KEY, usuario_id INTEGER NOT NULL, vence REAL NOT NULL);
CREATE TABLE IF NOT EXISTS hilos (
  id INTEGER PRIMARY KEY, autor_id INTEGER NOT NULL, titulo TEXT NOT NULL, texto TEXT NOT NULL,
  creado REAL NOT NULL, borrado INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS respuestas (
  id INTEGER PRIMARY KEY, hilo_id INTEGER NOT NULL, padre_id INTEGER, autor_id INTEGER NOT NULL,
  texto TEXT NOT NULL, creado REAL NOT NULL, borrado INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS votos (
  usuario_id INTEGER NOT NULL, tipo TEXT NOT NULL, objeto_id INTEGER NOT NULL, valor INTEGER NOT NULL,
  PRIMARY KEY (usuario_id, tipo, objeto_id));
"""


# Largo máximo de clave (128) para que nadie mande megabytes a scrypt.
class Credenciales(BaseModel):
    nombre: str = Field(min_length=3, max_length=24)
    clave: str = Field(min_length=8, max_length=128)


class HiloIn(BaseModel):
    titulo: str = Field(min_length=3, max_length=200)
    texto: str = Field(min_length=1, max_length=10_000)


class RespuestaIn(BaseModel):
    texto: str = Field(min_length=1, max_length=5_000)
    padre_id: int | None = None


# valor: 1 (a favor), -1 (en contra) o 0 (quitar el voto).
class VotoIn(BaseModel):
    tipo: str = Field(pattern="^(hilo|respuesta)$")
    id: int
    valor: int = Field(ge=-1, le=1)


# Reloj inyectable: los tests simulan días que pasan (vencimiento, ranking).
def crear_app(ruta_db: str = ":memory:", reloj: Callable[[], float] = time.time) -> FastAPI:
    app = FastAPI(title="Foro de discusión")
    con = sqlite3.connect(ruta_db, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(ESQUEMA)
    lock = threading.Lock()

    # Todas las escrituras pasan por acá: un lugar para el lock y el commit.
    def ejecutar(sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Escritura protegida por candado + commit."""
        with lock:
            cur = con.execute(sql, params)
            con.commit()
        return cur

    def usuario_actual(authorization: str = Header(default="")) -> sqlite3.Row:
        """Dependencia: valida 'Authorization: Bearer <token>'."""
        # WWW-Authenticate le indica al cliente qué esquema de auth se espera (RFC 6750).
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "Falta el token", headers={"WWW-Authenticate": "Bearer"})
        # authorization[7:] quita el prefijo "Bearer " (7 caracteres). Se busca por
        # huella y se exige que no haya vencido, todo en una sola consulta.
        f = con.execute("SELECT u.* FROM tokens t JOIN usuarios u ON u.id = t.usuario_id"
                        " WHERE t.huella = ? AND t.vence > ?", (huella_token(authorization[7:]), reloj())).fetchone()
        if f is None:
            raise HTTPException(401, "Token inválido o vencido", headers={"WWW-Authenticate": "Bearer"})
        return f

    # Puntaje = suma de votos (+1 y -1). COALESCE: sin votos => 0.
    def puntaje(tipo: str, oid: int) -> int:
        return con.execute("SELECT COALESCE(SUM(valor), 0) FROM votos WHERE tipo = ? AND objeto_id = ?",
                           (tipo, oid)).fetchone()[0]

    # Un hilo borrado se comporta como inexistente (404).
    def hilo_vivo(hid: int) -> sqlite3.Row:
        h = con.execute("SELECT h.*, u.nombre autor FROM hilos h JOIN usuarios u ON u.id = h.autor_id"
                        " WHERE h.id = ? AND h.borrado = 0", (hid,)).fetchone()
        if h is None:
            raise HTTPException(404, "Hilo no encontrado")
        return h

    # Datos de la lista de hilos. Calcular puntaje y conteo por hilo es N+1
    # consultas: aceptable en un foro chico; con volumen se usaría un JOIN/GROUP BY
    # o contadores desnormalizados.
    def resumen_hilo(h: sqlite3.Row) -> dict[str, Any]:
        p = puntaje("hilo", h["id"])
        n = con.execute("SELECT COUNT(*) FROM respuestas WHERE hilo_id = ? AND borrado = 0", (h["id"],)).fetchone()[0]
        return {"id": h["id"], "titulo": h["titulo"], "texto": h["texto"], "autor": h["autor"],
                "creado": h["creado"], "puntaje": p, "respuestas": n, "hot": puntaje_hot(p, h["creado"])}

    # ---------------- Auth ----------------
    @app.post("/registro", status_code=201)
    def registro(c: Credenciales):
        # fullmatch exige que TODO el nombre cumpla (match solo miraría el inicio).
        if not re.fullmatch(r"[A-Za-z0-9_]+", c.nombre):
            raise HTTPException(422, "Nombre: solo letras, números y guion bajo")
        try:
            ejecutar("INSERT INTO usuarios (nombre, hash) VALUES (?, ?)", (c.nombre, hashear_clave(c.clave)))
        # UNIQUE(nombre) => 409 Conflict.
        except sqlite3.IntegrityError as e:
            raise HTTPException(409, "Nombre en uso") from e
        return {"nombre": c.nombre}

    @app.post("/login")
    def login(c: Credenciales):
        u = con.execute("SELECT * FROM usuarios WHERE nombre = ?", (c.nombre,)).fetchone()
        # Mismo mensaje para usuario inexistente y clave incorrecta.
        if u is None or not verificar_clave(c.clave, u["hash"]):
            raise HTTPException(401, "Credenciales inválidas")
        # El token en claro se devuelve una única vez al cliente; en la base queda
        # solo su huella con la fecha de vencimiento.
        token = nuevo_token()
        ejecutar("INSERT INTO tokens VALUES (?, ?, ?)", (huella_token(token), u["id"], reloj() + DURACION_TOKEN))
        return {"token": token, "tipo": "Bearer"}

    @app.post("/logout", status_code=204)
    # Depends(usuario_actual) garantiza que el token sea válido antes de borrarlo.
    def logout(authorization: str = Header(default=""), _u=Depends(usuario_actual)):
        ejecutar("DELETE FROM tokens WHERE huella = ?", (huella_token(authorization[7:]),))

    # ---------------- Hilos ----------------
    @app.get("/hilos")
    def listar(orden: str = "populares", limite: int = 25):
        hs = [resumen_hilo(h) for h in con.execute(
            "SELECT h.*, u.nombre autor FROM hilos h JOIN usuarios u ON u.id = h.autor_id WHERE h.borrado = 0")]
        # Funciones de orden por modo; en "top" el desempate es por más reciente.
        claves = {"nuevos": lambda x: x["creado"], "top": lambda x: (x["puntaje"], x["creado"]),
                  "populares": lambda x: x["hot"]}
        if orden not in claves:
            raise HTTPException(422, "orden debe ser nuevos, top o populares")
        # El límite se acota a 1..100 aunque el cliente pida otra cosa.
        return sorted(hs, key=claves[orden], reverse=True)[: max(1, min(limite, 100))]

    @app.post("/hilos", status_code=201)
    def crear_hilo(h: HiloIn, u=Depends(usuario_actual)):
        cur = ejecutar("INSERT INTO hilos (autor_id, titulo, texto, creado) VALUES (?, ?, ?, ?)",
                       (u["id"], h.titulo, h.texto, reloj()))
        return resumen_hilo(hilo_vivo(cur.lastrowid))

    @app.get("/hilos/{hid}")
    def ver_hilo(hid: int):
        """Devuelve el hilo con su árbol de respuestas (ordenadas por puntaje)."""
        h = hilo_vivo(hid)
        filas = con.execute("SELECT r.*, u.nombre autor FROM respuestas r JOIN usuarios u ON u.id = r.autor_id"
                            " WHERE r.hilo_id = ? ORDER BY r.id", (hid,)).fetchall()
        # Armado del árbol en dos pasadas, O(n): 1) crear un nodo por respuesta
        # indexado por id; 2) colgar cada nodo de su padre (o de la raíz).
        # Funciona porque se trae todo el hilo de una vez, ordenado por id.
        nodos: dict[int, dict[str, Any]] = {}
        for r in filas:
            # Las respuestas borradas se muestran como "[borrado]" para no romper el árbol
            nodos[r["id"]] = {"id": r["id"], "autor": None if r["borrado"] else r["autor"],
                              "texto": "[borrado]" if r["borrado"] else r["texto"],
                              "puntaje": puntaje("respuesta", r["id"]), "padre_id": r["padre_id"], "hijos": []}
        # Segunda pasada: los nodos son dicts compartidos, así que agregarlos a la
        # lista "hijos" del padre arma el árbol sin copiar nada.
        raiz: list[dict[str, Any]] = []
        for n in nodos.values():
            (nodos[n["padre_id"]]["hijos"] if n["padre_id"] else raiz).append(n)

        # Orden recursivo en cada nivel: más votadas primero; a igual puntaje, la
        # más antigua (id menor). La profundidad está acotada por lo que escriban
        # los usuarios; para árboles enormes convendría un límite.
        def ordenar(lista: list[dict[str, Any]]) -> None:
            lista.sort(key=lambda x: (-x["puntaje"], x["id"]))
            for x in lista:
                ordenar(x["hijos"])
        ordenar(raiz)
        return {**resumen_hilo(h), "arbol": raiz}

    @app.delete("/hilos/{hid}", status_code=204)
    def borrar_hilo(hid: int, u=Depends(usuario_actual)):
        # 404 si no existe (lo lanza hilo_vivo) y 403 si no es el autor.
        if hilo_vivo(hid)["autor_id"] != u["id"]:
            raise HTTPException(403, "Solo el autor puede borrar")
        ejecutar("UPDATE hilos SET borrado = 1 WHERE id = ?", (hid,))

    # ---------------- Respuestas ----------------
    @app.post("/hilos/{hid}/respuestas", status_code=201)
    def responder(hid: int, r: RespuestaIn, u=Depends(usuario_actual)):
        hilo_vivo(hid)
        if r.padre_id is not None:
            padre = con.execute("SELECT hilo_id FROM respuestas WHERE id = ?", (r.padre_id,)).fetchone()
            # Evita colgar una respuesta de un padre que está en otro hilo (árbol roto).
            if padre is None or padre["hilo_id"] != hid:
                raise HTTPException(422, "La respuesta padre no pertenece a este hilo")
        cur = ejecutar("INSERT INTO respuestas (hilo_id, padre_id, autor_id, texto, creado) VALUES (?, ?, ?, ?, ?)",
                       (hid, r.padre_id, u["id"], r.texto, reloj()))
        return {"id": cur.lastrowid}

    @app.delete("/respuestas/{rid}", status_code=204)
    def borrar_respuesta(rid: int, u=Depends(usuario_actual)):
        r = con.execute("SELECT * FROM respuestas WHERE id = ? AND borrado = 0", (rid,)).fetchone()
        if r is None:
            raise HTTPException(404, "Respuesta no encontrada")
        if r["autor_id"] != u["id"]:
            raise HTTPException(403, "Solo el autor puede borrar")
        ejecutar("UPDATE respuestas SET borrado = 1 WHERE id = ?", (rid,))

    # ---------------- Votos ----------------
    @app.post("/votos")
    def votar(v: VotoIn, u=Depends(usuario_actual)):
        # El nombre de tabla va por f-string, pero solo puede ser uno de estos dos
        # valores fijos (el pattern del modelo ya restringe `tipo`).
        tabla = "hilos" if v.tipo == "hilo" else "respuestas"
        if con.execute(f"SELECT 1 FROM {tabla} WHERE id = ? AND borrado = 0", (v.id,)).fetchone() is None:
            raise HTTPException(404, "Objeto no encontrado")
        # Valor 0 = quitar el voto (el puntaje vuelve a como estaba sin él).
        if v.valor == 0:
            ejecutar("DELETE FROM votos WHERE usuario_id = ? AND tipo = ? AND objeto_id = ?", (u["id"], v.tipo, v.id))
        else:
            # UPSERT: un único voto por usuario y objeto; se puede cambiar de +1 a -1
            ejecutar("INSERT INTO votos VALUES (?, ?, ?, ?) ON CONFLICT(usuario_id, tipo, objeto_id)"
                     " DO UPDATE SET valor = excluded.valor", (u["id"], v.tipo, v.id, v.valor))
        return {"puntaje": puntaje(v.tipo, v.id)}

    return app


app = crear_app(os.environ.get("FORO_DB", ":memory:"))
