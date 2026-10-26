"""Capa HTTP (FastAPI) sobre el servicio de inventario."""
from __future__ import annotations

import os

# Esta capa es delgada a propósito: valida la entrada y delega todo al
# servicio, que se puede testear y reutilizar (CLI, otra API) sin HTTP.
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# ErrorInventario lleva su propio código HTTP; un solo handler lo traduce.
from inventario.servicio import ErrorInventario, Inventario


class ProductoIn(BaseModel):
    # SKU: letras, dígitos y guiones (2-32). Sin espacios para que sea fácil de
    # escanear o tipear. Se normaliza a mayúsculas en el servicio.
    sku: str = Field(pattern=r"^[A-Za-z0-9\-]{2,32}$")
    nombre: str = Field(min_length=1, max_length=120)
    # Punto de reorden: cuando el stock total baja a este valor o menos, alerta.
    punto_reorden: int = Field(default=0, ge=0)


class AlmacenIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=80)


# Un mismo modelo sirve para entrada, salida y ajuste. La cantidad no se
# restringe acá (ge=1) porque las reglas difieren por tipo y las aplica el
# servicio (p. ej. el ajuste acepta 0).
class MovimientoIn(BaseModel):
    producto_id: int
    almacen_id: int
    cantidad: int
    # Solo se usa en las entradas (es el costo de compra de esa partida).
    costo_unitario: float | None = None
    nota: str = ""


# origen y destino son ids de almacén.
class TransferenciaIn(BaseModel):
    producto_id: int
    origen: int
    destino: int
    cantidad: int


def crear_app(ruta_db: str = ":memory:") -> FastAPI:
    app = FastAPI(title="API de inventario")
    # Una instancia de servicio por app (cada test obtiene la suya).
    inv = Inventario(ruta_db)

    # Sin este handler, un ErrorInventario sería un 500. Con él, el servicio
    # decide el código (404 inexistente, 409 conflicto de stock, 400 inválido).
    @app.exception_handler(ErrorInventario)
    async def manejar_error(_r: Request, e: ErrorInventario):
        """Convierte errores de negocio en respuestas JSON con su código HTTP."""
        return JSONResponse(status_code=e.codigo, content={"detail": str(e)})

    @app.post("/productos", status_code=201)
    def crear_producto(p: ProductoIn):
        return inv.crear_producto(p.sku, p.nombre, p.punto_reorden)

    @app.post("/almacenes", status_code=201)
    def crear_almacen(a: AlmacenIn):
        return inv.crear_almacen(a.nombre)

    @app.post("/movimientos/entrada")
    def entrada(m: MovimientoIn):
        # `or 0`: si no se informa costo, la partida entra a costo 0.
        return {"stock": inv.entrada(m.producto_id, m.almacen_id, m.cantidad, m.costo_unitario or 0, m.nota)}

    @app.post("/movimientos/salida")
    def salida(m: MovimientoIn):
        return {"stock": inv.salida(m.producto_id, m.almacen_id, m.cantidad, m.nota)}

    # En el ajuste, `cantidad` es la cantidad REAL contada (no un delta).
    @app.post("/movimientos/ajuste")
    def ajuste(m: MovimientoIn):
        return {"stock": inv.ajuste(m.producto_id, m.almacen_id, m.cantidad, m.nota)}

    @app.post("/movimientos/transferencia")
    def transferencia(t: TransferenciaIn):
        return inv.transferir(t.producto_id, t.origen, t.destino, t.cantidad)

    @app.get("/productos/{pid}/stock")
    def stock(pid: int):
        return inv.stock_producto(pid)

    @app.get("/productos/{pid}/kardex")
    def kardex(pid: int):
        return inv.kardex(pid)

    @app.get("/alertas/bajo-stock")
    def bajo_stock():
        return inv.bajo_stock()

    # Valor del inventario = suma de stock x costo promedio de cada producto.
    @app.get("/reportes/valuacion")
    def valuacion():
        return {"valor_total": inv.valuacion_total()}

    return app


app = crear_app(os.environ.get("INVENTARIO_DB", ":memory:"))
