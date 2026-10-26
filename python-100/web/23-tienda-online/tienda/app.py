"""API de la tienda: catálogo, carritos y checkout.

Los importes se manejan SIEMPRE en centavos (enteros) para evitar errores de
redondeo de los float. La administración del catálogo requiere el header
`X-Admin-Token`, cuyo valor sale de la variable de entorno TIENDA_ADMIN_TOKEN.
"""
from __future__ import annotations

import os
# secrets: ids de carrito no adivinables y comparación de tokens en tiempo constante.
import secrets
import sqlite3
# Un único lock serializa las escrituras: con SQLite y una sola conexión
# compartida es la forma más simple de evitar condiciones de carrera.
import threading
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

# La app depende del Protocolo PasarelaPago, no de una pasarela concreta.
from tienda.pagos import PasarelaPago, PasarelaSimulada

# Esquema:
# - productos: los CHECK de la base garantizan precio > 0 y stock >= 0 aunque
#   un bug en Python intentara grabar otra cosa.
# - carritos: id de texto aleatorio; cerrado=1 cuando ya se pagó.
# - items_carrito: PK compuesta (carrito, producto) => un renglón por producto.
# - pedidos: carrito_id UNIQUE (un carrito se paga una sola vez) e
#   idempotencia UNIQUE (una misma clave no genera dos pedidos).
ESQUEMA = """
CREATE TABLE IF NOT EXISTS productos (
  id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL,
  precio_centavos INTEGER NOT NULL CHECK (precio_centavos > 0),
  stock INTEGER NOT NULL CHECK (stock >= 0), activo INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS carritos (id TEXT PRIMARY KEY, cerrado INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS items_carrito (
  carrito_id TEXT NOT NULL, producto_id INTEGER NOT NULL, cantidad INTEGER NOT NULL,
  PRIMARY KEY (carrito_id, producto_id));
CREATE TABLE IF NOT EXISTS pedidos (
  id INTEGER PRIMARY KEY AUTOINCREMENT, carrito_id TEXT UNIQUE NOT NULL,
  total_centavos INTEGER NOT NULL, transaccion TEXT NOT NULL, ultimos4 TEXT NOT NULL,
  idempotencia TEXT UNIQUE);
"""


# Validación de entrada del catálogo (422 automático si falla).
class ProductoEntrada(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    # Entero en centavos: $15,00 se guarda como 1500.
    precio_centavos: int = Field(gt=0)
    stock: int = Field(ge=0)


class ItemEntrada(BaseModel):
    producto_id: int
    # Tope de 100 unidades por renglón para evitar pedidos absurdos.
    cantidad: int = Field(ge=1, le=100)


class DatosPago(BaseModel):
    """Datos de tarjeta: se usan para cobrar y se descartan (no se persisten)."""
    # 23 = 19 dígitos (máximo de una tarjeta) + 4 espacios/guiones de formato.
    numero_tarjeta: str = Field(min_length=12, max_length=23)
    cvv: str = Field(min_length=3, max_length=4)
    # Formato MM/AA; el mes y si está vencida se validan en la pasarela.
    vencimiento: str = Field(pattern=r"^\d{2}/\d{2}$")


def crear_app(ruta_db: str = ":memory:", pasarela: PasarelaPago | None = None,
              token_admin: str | None = None) -> FastAPI:
    """Fábrica de la app; la pasarela es inyectable (simulada por defecto)."""
    app = FastAPI(title="Tienda online", version="1.0.0")
    # Una conexión compartida por toda la app (FastAPI atiende en un pool de hilos).
    con = sqlite3.connect(ruta_db, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(ESQUEMA)
    lock = threading.Lock()
    pasarela = pasarela or PasarelaSimulada()
    # Si no hay token configurado, la administración queda deshabilitada (401 siempre).
    token_admin = token_admin or os.environ.get("TIENDA_ADMIN_TOKEN")

    def es_admin(x_admin_token: str | None = Header(default=None)) -> None:
        """Dependencia: exige el token de administración correcto."""
        # compare_digest evita ataques de tiempo al comparar el token.
        if not token_admin or not x_admin_token or not secrets.compare_digest(x_admin_token, token_admin):
            raise HTTPException(401, "Se requiere token de administrador")

    def carrito_abierto(cid: str) -> sqlite3.Row:
        """Obtiene un carrito existente y no cerrado."""
        c = con.execute("SELECT * FROM carritos WHERE id = ?", (cid,)).fetchone()
        if c is None:
            raise HTTPException(404, "Carrito no encontrado")
        # 409 Conflict: el recurso existe pero su estado no permite la operación.
        if c["cerrado"]:
            raise HTTPException(409, "El carrito ya fue pagado")
        return c

    def detalle_carrito(cid: str) -> dict[str, Any]:
        """Arma el detalle del carrito con subtotales y total."""
        filas = con.execute(
            "SELECT p.id, p.nombre, p.precio_centavos, i.cantidad FROM items_carrito i"
            " JOIN productos p ON p.id = i.producto_id WHERE i.carrito_id = ? ORDER BY p.id", (cid,)).fetchall()
        # Subtotal = precio unitario actual x cantidad (precios vivos del catálogo).
        items = [{**dict(f), "subtotal_centavos": f["precio_centavos"] * f["cantidad"]} for f in filas]
        return {"id": cid, "items": items, "total_centavos": sum(i["subtotal_centavos"] for i in items)}

    # --------- Catálogo ---------
    @app.get("/productos")
    def listar_productos():
        # Solo productos activos: los dados de baja no se venden pero no se borran.
        return [dict(f) for f in con.execute("SELECT id, nombre, precio_centavos, stock FROM productos WHERE activo = 1")]

    # dependencies=[...] ejecuta la verificación sin pasar nada a la función.
    @app.post("/productos", status_code=201, dependencies=[Depends(es_admin)])
    def crear_producto(p: ProductoEntrada):
        with lock:
            cur = con.execute("INSERT INTO productos (nombre, precio_centavos, stock) VALUES (?, ?, ?)",
                              (p.nombre, p.precio_centavos, p.stock))
            con.commit()
        return {"id": cur.lastrowid, **p.model_dump()}

    @app.put("/productos/{pid}", dependencies=[Depends(es_admin)])
    def actualizar_producto(pid: int, p: ProductoEntrada):
        with lock:
            cur = con.execute("UPDATE productos SET nombre=?, precio_centavos=?, stock=? WHERE id=?",
                              (p.nombre, p.precio_centavos, p.stock, pid))
            con.commit()
        # rowcount 0 => no había producto con ese id.
        if cur.rowcount == 0:
            raise HTTPException(404, "Producto no encontrado")
        return {"id": pid, **p.model_dump()}

    @app.delete("/productos/{pid}", status_code=204, dependencies=[Depends(es_admin)])
    def desactivar_producto(pid: int):
        # Borrado lógico: los pedidos viejos siguen referenciando el producto
        with lock:
            con.execute("UPDATE productos SET activo = 0 WHERE id = ?", (pid,))
            con.commit()

    # --------- Carrito ---------
    @app.post("/carritos", status_code=201)
    def crear_carrito():
        # Id aleatorio no adivinable: funciona como "llave" del carrito anónimo
        cid = secrets.token_urlsafe(16)
        with lock:
            con.execute("INSERT INTO carritos (id) VALUES (?)", (cid,))
            con.commit()
        return {"id": cid}

    @app.get("/carritos/{cid}")
    def ver_carrito(cid: str):
        if con.execute("SELECT 1 FROM carritos WHERE id = ?", (cid,)).fetchone() is None:
            raise HTTPException(404, "Carrito no encontrado")
        return detalle_carrito(cid)

    @app.put("/carritos/{cid}/items")
    # PUT con cantidad absoluta (no "sumar 1"): repetir el pedido da el mismo
    # resultado, lo que hace seguro reintentarlo ante un corte de red.
    def poner_item(cid: str, item: ItemEntrada):
        """Fija la cantidad de un producto en el carrito (idempotente)."""
        carrito_abierto(cid)
        prod = con.execute("SELECT * FROM productos WHERE id = ? AND activo = 1", (item.producto_id,)).fetchone()
        if prod is None:
            raise HTTPException(404, "Producto no encontrado")
        # Validación temprana de stock (se vuelve a validar en el checkout).
        if item.cantidad > prod["stock"]:
            raise HTTPException(409, f"Stock insuficiente (disponible: {prod['stock']})")
        with lock:
            # UPSERT: si el renglón ya existe, se reemplaza la cantidad ("excluded" es
            # la fila que se intentó insertar).
            con.execute("INSERT INTO items_carrito VALUES (?, ?, ?) ON CONFLICT(carrito_id, producto_id)"
                        " DO UPDATE SET cantidad = excluded.cantidad", (cid, item.producto_id, item.cantidad))
            con.commit()
        return detalle_carrito(cid)

    @app.delete("/carritos/{cid}/items/{pid}")
    def quitar_item(cid: str, pid: int):
        carrito_abierto(cid)
        # Toda la operación de checkout va bajo el lock: dos pagos simultáneos del
        # mismo stock no pueden intercalarse.
        with lock:
            con.execute("DELETE FROM items_carrito WHERE carrito_id = ? AND producto_id = ?", (cid, pid))
            con.commit()
        return detalle_carrito(cid)

    # --------- Checkout ---------
    @app.post("/carritos/{cid}/checkout", status_code=201)
    def checkout(cid: str, pago: DatosPago, idempotency_key: str | None = Header(default=None)):
        """Cobra el carrito y descuenta stock en una sola transacción.

        Si se reenvía la misma `Idempotency-Key`, se devuelve el pedido ya
        creado en lugar de cobrar dos veces (protección ante doble clic).
        """
        with lock:
            # Si ya existe un pedido con esta clave se devuelve tal cual, sin volver a
            # cobrar (doble clic, reintento del cliente, etc.).
            if idempotency_key:
                previo = con.execute("SELECT * FROM pedidos WHERE idempotencia = ?", (idempotency_key,)).fetchone()
                if previo:
                    return dict(previo)
            carrito_abierto(cid)
            det = detalle_carrito(cid)
            if not det["items"]:
                raise HTTPException(400, "El carrito está vacío")
            # Revalida stock justo antes de cobrar
            # Entre que se armó el carrito y se paga, otro cliente pudo comprar el
            # último ítem: por eso se relee el stock acá.
            for it in det["items"]:
                stock = con.execute("SELECT stock FROM productos WHERE id = ?", (it["id"],)).fetchone()[0]
                if it["cantidad"] > stock:
                    raise HTTPException(409, f"Stock insuficiente para {it['nombre']}")
            # Recién con todo validado se llama a la pasarela.
            res = pasarela.cobrar(det["total_centavos"], pago.numero_tarjeta, pago.cvv, pago.vencimiento)
            if not res.aprobado:
                # 402 Payment Required: pago rechazado. No se tocó stock ni carrito.
                raise HTTPException(402, res.motivo)
            # Descuento de stock + cierre del carrito + pedido: todo o nada.
            # (En una pasarela real, si esto fallara habría que reembolsar el cobro.)
            try:
                for it in det["items"]:
                    con.execute("UPDATE productos SET stock = stock - ? WHERE id = ?", (it["cantidad"], it["id"]))
                con.execute("UPDATE carritos SET cerrado = 1 WHERE id = ?", (cid,))
                cur = con.execute("INSERT INTO pedidos (carrito_id, total_centavos, transaccion, ultimos4, idempotencia)"
                                  " VALUES (?, ?, ?, ?, ?)", (cid, det["total_centavos"], res.id_transaccion,
                                                             res.ultimos4, idempotency_key))
                con.commit()
            # Ante cualquier error se deshace la transacción y se propaga (500).
            except sqlite3.Error:
                con.rollback()
                raise
            # Solo se devuelven los últimos 4 dígitos; el número completo nunca se guarda.
            return dict(con.execute("SELECT * FROM pedidos WHERE id = ?", (cur.lastrowid,)).fetchone())

    return app


# Instancia para `uvicorn tienda.app:app`.
app = crear_app(os.environ.get("TIENDA_DB", ":memory:"))
