"""Lógica de negocio del inventario (independiente de la capa HTTP).

Conceptos:
- Producto: SKU único, punto de reorden (stock mínimo deseado).
- Almacén: lugar físico donde hay stock.
- Movimiento: ENTRADA, SALIDA, AJUSTE o TRANSFERENCIA. Todo cambio de stock
  queda registrado (kardex) y nunca se edita: así hay trazabilidad completa.
- Costo promedio ponderado: cada ENTRADA recalcula el costo unitario del producto.
"""
from __future__ import annotations

import sqlite3
import threading
from typing import Any

# Tablas:
# - productos.costo_promedio se actualiza en cada entrada.
# - stock: una fila por (producto, almacén). El CHECK cantidad >= 0 es la
#   última barrera contra stock negativo, aunque el código ya lo valida.
# - movimientos: libro de solo-agregar (append-only), base del kardex.
#   La cantidad tiene signo: + entra, - sale.
ESQUEMA = """
CREATE TABLE IF NOT EXISTS productos (
  id INTEGER PRIMARY KEY AUTOINCREMENT, sku TEXT UNIQUE NOT NULL, nombre TEXT NOT NULL,
  punto_reorden INTEGER NOT NULL DEFAULT 0, costo_promedio REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS almacenes (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS stock (
  producto_id INTEGER NOT NULL REFERENCES productos(id), almacen_id INTEGER NOT NULL REFERENCES almacenes(id),
  cantidad INTEGER NOT NULL CHECK (cantidad >= 0), PRIMARY KEY (producto_id, almacen_id));
CREATE TABLE IF NOT EXISTS movimientos (
  id INTEGER PRIMARY KEY AUTOINCREMENT, producto_id INTEGER NOT NULL, almacen_id INTEGER NOT NULL,
  tipo TEXT NOT NULL, cantidad INTEGER NOT NULL, costo_unitario REAL, nota TEXT NOT NULL DEFAULT '',
  momento TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
"""


# Excepción de dominio: el servicio no sabe nada de HTTP, solo sugiere un
# código que la capa web usa tal cual.
class ErrorInventario(Exception):
    """Error de negocio (se traduce a 4xx en la API)."""

    def __init__(self, mensaje: str, codigo: int = 400) -> None:
        super().__init__(mensaje)
        self.codigo = codigo


class Inventario:
    """Servicio con todas las operaciones; cada operación es una transacción."""

    def __init__(self, ruta: str = ":memory:") -> None:
        # isolation_level=None = modo autocommit del driver: las transacciones se
        # manejan a mano con BEGIN/COMMIT en _tx() (más explícito y predecible).
        self.con = sqlite3.connect(ruta, check_same_thread=False, isolation_level=None)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys = ON")
        self.con.executescript(ESQUEMA)
        # Lock por instancia: serializa las transacciones entre hilos.
        self.lock = threading.Lock()

    # ------------------------- helpers -------------------------
    # Se implementa como clase interna para mostrar el protocolo de context
    # manager (__enter__/__exit__); contextlib.contextmanager sería equivalente.
    def _tx(self):
        """Context manager simple: BEGIN/COMMIT o ROLLBACK ante error."""
        servicio = self

        class _T:
            def __enter__(self):
                servicio.lock.acquire()
                # IMMEDIATE toma el lock de escritura de SQLite al comenzar: otro proceso
                # no puede escribir entre nuestra lectura de stock y nuestra escritura.
                servicio.con.execute("BEGIN IMMEDIATE")
                return servicio.con

            def __exit__(self, tipo, *_):
                try:
                    # `tipo` es la clase de la excepción (o None si todo salió bien).
                    servicio.con.execute("ROLLBACK" if tipo else "COMMIT")
                finally:
                    # finally: el lock se libera siempre, aunque el ROLLBACK fallara.
                    servicio.lock.release()
                # False => la excepción original (si la hubo) se propaga al que llamó.
                return False
        return _T()

    def _producto(self, pid: int) -> sqlite3.Row:
        p = self.con.execute("SELECT * FROM productos WHERE id = ?", (pid,)).fetchone()
        if p is None:
            raise ErrorInventario("Producto inexistente", 404)
        return p

    def _almacen(self, aid: int) -> None:
        if self.con.execute("SELECT 1 FROM almacenes WHERE id = ?", (aid,)).fetchone() is None:
            raise ErrorInventario("Almacén inexistente", 404)

    def _cantidad(self, pid: int, aid: int) -> int:
        f = self.con.execute("SELECT cantidad FROM stock WHERE producto_id = ? AND almacen_id = ?", (pid, aid)).fetchone()
        # Sin fila de stock => 0 unidades (todavía no entró nada a ese almacén).
        return f[0] if f else 0

    def _sumar(self, con: sqlite3.Connection, pid: int, aid: int, delta: int) -> int:
        """Suma `delta` al stock; falla si quedaría negativo."""
        # delta positivo suma, negativo resta. Toda modificación de stock pasa por
        # acá, así la regla "nunca negativo" está en un solo lugar.
        nuevo = self._cantidad(pid, aid) + delta
        if nuevo < 0:
            # nuevo - delta = cantidad que había antes del movimiento.
            raise ErrorInventario(f"Stock insuficiente (disponible {nuevo - delta})", 409)
        # UPSERT: crea la fila la primera vez o actualiza la cantidad si ya existe.
        con.execute("INSERT INTO stock VALUES (?, ?, ?) ON CONFLICT(producto_id, almacen_id)"
                    " DO UPDATE SET cantidad = excluded.cantidad", (pid, aid, nuevo))
        return nuevo

    # Cada cambio de stock deja su movimiento en la MISMA transacción: no puede
    # haber stock sin historia ni historia sin stock.
    def _registrar(self, con, pid, aid, tipo, cant, costo=None, nota="") -> None:
        con.execute("INSERT INTO movimientos (producto_id, almacen_id, tipo, cantidad, costo_unitario, nota)"
                    " VALUES (?, ?, ?, ?, ?, ?)", (pid, aid, tipo, cant, costo, nota))

    # ------------------------- altas -------------------------
    def crear_producto(self, sku: str, nombre: str, punto_reorden: int = 0) -> dict[str, Any]:
        try:
            with self._tx() as con:
                cur = con.execute("INSERT INTO productos (sku, nombre, punto_reorden) VALUES (?, ?, ?)",
                                  # upper(): "torn-01" y "TORN-01" son el mismo SKU.
                                  (sku.upper(), nombre, punto_reorden))
        # La restricción UNIQUE de la base detecta el duplicado => 409.
        except sqlite3.IntegrityError as e:
            raise ErrorInventario("SKU duplicado", 409) from e
        return dict(self._producto(cur.lastrowid))

    def crear_almacen(self, nombre: str) -> dict[str, Any]:
        try:
            with self._tx() as con:
                cur = con.execute("INSERT INTO almacenes (nombre) VALUES (?)", (nombre,))
        except sqlite3.IntegrityError as e:
            raise ErrorInventario("Almacén duplicado", 409) from e
        return {"id": cur.lastrowid, "nombre": nombre}

    # ------------------------- movimientos -------------------------
    def entrada(self, pid: int, aid: int, cantidad: int, costo_unitario: float, nota: str = "") -> int:
        """Recepción de mercadería: suma stock y recalcula el costo promedio ponderado."""
        # Las validaciones van antes de abrir la transacción (fallan barato).
        if cantidad <= 0 or costo_unitario < 0:
            raise ErrorInventario("Cantidad debe ser > 0 y costo >= 0")
        p = self._producto(pid)
        self._almacen(aid)
        with self._tx() as con:
            # El costo promedio es por producto (todos los almacenes juntos), por eso
            # se usa el stock total y no el del almacén que recibe.
            existente = self.total_producto(pid)
            # promedio = (stock*costo_actual + cantidad*costo_nuevo) / (stock + cantidad)
            # Ej.: 10 u. a $100 + 30 u. a $200 => (1000 + 6000) / 40 = $175.
            # No hay división por cero: cantidad > 0 está validado arriba.
            nuevo_costo = (existente * p["costo_promedio"] + cantidad * costo_unitario) / (existente + cantidad)
            con.execute("UPDATE productos SET costo_promedio = ? WHERE id = ?", (round(nuevo_costo, 4), pid))
            nuevo = self._sumar(con, pid, aid, cantidad)
            self._registrar(con, pid, aid, "ENTRADA", cantidad, costo_unitario, nota)
        return nuevo

    def salida(self, pid: int, aid: int, cantidad: int, nota: str = "") -> int:
        """Despacho: resta stock (nunca por debajo de cero)."""
        if cantidad <= 0:
            raise ErrorInventario("Cantidad debe ser > 0")
        self._producto(pid)
        self._almacen(aid)
        with self._tx() as con:
            nuevo = self._sumar(con, pid, aid, -cantidad)
            # Se registra en negativo para que el saldo del kardex sea una suma simple.
            # Las salidas no cambian el costo promedio (salen al costo vigente).
            self._registrar(con, pid, aid, "SALIDA", -cantidad, None, nota)
        return nuevo

    def ajuste(self, pid: int, aid: int, cantidad_real: int, nota: str) -> int:
        """Ajuste por conteo físico: fija el stock al valor contado."""
        # Un ajuste sin justificación sería imposible de auditar: se exige nota.
        if cantidad_real < 0 or not nota:
            raise ErrorInventario("El ajuste requiere cantidad >= 0 y una nota justificativa")
        self._producto(pid)
        self._almacen(aid)
        with self._tx() as con:
            # El movimiento guarda la diferencia (ej.: había 6, se contaron 5 => -1).
            delta = cantidad_real - self._cantidad(pid, aid)
            self._sumar(con, pid, aid, delta)
            self._registrar(con, pid, aid, "AJUSTE", delta, None, nota)
        return cantidad_real

    def transferir(self, pid: int, origen: int, destino: int, cantidad: int) -> dict[str, int]:
        """Mueve stock entre almacenes de forma atómica (o se hace todo o nada)."""
        # Transferir a sí mismo no tiene sentido y ensuciaría el kardex.
        if origen == destino or cantidad <= 0:
            raise ErrorInventario("Transferencia inválida")
        self._producto(pid)
        self._almacen(origen)
        self._almacen(destino)
        with self._tx() as con:
            # Si el origen no alcanza, _sumar lanza error y la transacción hace
            # ROLLBACK: el destino nunca recibe nada (atomicidad).
            a = self._sumar(con, pid, origen, -cantidad)
            b = self._sumar(con, pid, destino, cantidad)
            # Dos movimientos (salida del origen y entrada al destino) con nota cruzada.
            self._registrar(con, pid, origen, "TRANSFERENCIA", -cantidad, None, f"a almacén {destino}")
            self._registrar(con, pid, destino, "TRANSFERENCIA", cantidad, None, f"desde almacén {origen}")
        return {"origen": a, "destino": b}

    # ------------------------- consultas -------------------------
    def total_producto(self, pid: int) -> int:
        return self.con.execute("SELECT COALESCE(SUM(cantidad), 0) FROM stock WHERE producto_id = ?", (pid,)).fetchone()[0]

    def stock_producto(self, pid: int) -> dict[str, Any]:
        p = self._producto(pid)
        # Desglose por almacén, ordenado por nombre para tener una salida estable.
        por_alm = {f["nombre"]: f["cantidad"] for f in self.con.execute(
            "SELECT a.nombre, s.cantidad FROM stock s JOIN almacenes a ON a.id = s.almacen_id"
            " WHERE s.producto_id = ? ORDER BY a.nombre", (pid,))}
        total = sum(por_alm.values())
        return {"sku": p["sku"], "total": total, "por_almacen": por_alm,
                "costo_promedio": p["costo_promedio"], "valor": round(total * p["costo_promedio"], 2)}

    def bajo_stock(self) -> list[dict[str, Any]]:
        """Productos cuyo stock total está en o por debajo del punto de reorden."""
        filas = self.con.execute(
            # LEFT JOIN: incluye productos que nunca tuvieron stock (total 0).
            # HAVING filtra después de agrupar (WHERE no puede usar el SUM).
            "SELECT p.id, p.sku, p.nombre, p.punto_reorden, COALESCE(SUM(s.cantidad), 0) total"
            " FROM productos p LEFT JOIN stock s ON s.producto_id = p.id GROUP BY p.id"
            " HAVING total <= p.punto_reorden ORDER BY p.sku").fetchall()
        # Sugerencia de compra simple: reponer hasta el doble del punto de reorden.
        return [{**dict(f), "a_pedir": f["punto_reorden"] * 2 - f["total"]} for f in filas]

    def kardex(self, pid: int) -> list[dict[str, Any]]:
        """Historial de movimientos con saldo acumulado."""
        self._producto(pid)
        # Saldo acumulado: como las cantidades tienen signo, basta con sumarlas en
        # orden cronológico (ORDER BY id = orden de inserción).
        saldo = 0
        salida = []
        for m in self.con.execute("SELECT * FROM movimientos WHERE producto_id = ? ORDER BY id", (pid,)):
            saldo += m["cantidad"]
            salida.append({**dict(m), "saldo": saldo})
        return salida

    def valuacion_total(self) -> float:
        """Valor total del inventario a costo promedio."""
        return round(self.con.execute(
            "SELECT COALESCE(SUM(s.cantidad * p.costo_promedio), 0) FROM stock s JOIN productos p ON p.id = s.producto_id"
        ).fetchone()[0], 2)
