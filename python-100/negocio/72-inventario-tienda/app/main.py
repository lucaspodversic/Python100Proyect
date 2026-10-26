"""API + frontend del gestor de inventario.

- ``GET /`` sirve una página HTML (sin dependencias JS) que consume la API.
- El resto de rutas son JSON. ``crear_app`` permite crear apps aisladas en tests.

Ejecutar::

    export INVENTARIO_ADMIN_PASSWORD="..."
    uvicorn app.main:app --reload
"""
from __future__ import annotations

import os
from importlib import resources

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import servicio
from .auth import crear_auth, crear_usuario
from .db import Base, crear_fabrica_sesiones, crear_motor
from .modelos import Movimiento, Producto, Proveedor, Rol, TipoMovimiento, Usuario, Token


# ---------- Esquemas Pydantic ----------
class ProveedorIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    telefono: str = Field(default="", max_length=40)


class ProveedorOut(ProveedorIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class ProductoIn(BaseModel):
    sku: str = Field(pattern=r"^[A-Z0-9-]{3,40}$", description="Código interno en mayúsculas")
    nombre: str = Field(min_length=1, max_length=200)
    precio_centavos: int = Field(ge=0)
    stock_minimo: int = Field(default=0, ge=0)
    proveedor_id: int | None = None


class ProductoOut(ProductoIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    stock: int


class MovimientoIn(BaseModel):
    producto_id: int
    tipo: TipoMovimiento
    cantidad: int
    motivo: str = Field(default="", max_length=200)


class MovimientoOut(MovimientoIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    stock_resultante: int
    usuario_id: int


class LineaIn(BaseModel):
    producto_id: int
    cantidad: int


class OrdenIn(BaseModel):
    proveedor_id: int
    lineas: list[LineaIn]


class RolIn(BaseModel):
    rol: Rol


def crear_app(url_bd: str = "sqlite:///inventario.db", admin_email: str = "admin@tienda.local",
              admin_password: str | None = None) -> FastAPI:
    """Construye la app con su BD; crea el admin inicial si hay contraseña."""
    app = FastAPI(title="Inventario de tienda", version="1.0.0")
    motor = crear_motor(url_bd)
    Base.metadata.create_all(motor)
    fabrica = crear_fabrica_sesiones(motor)
    app.state.fabrica = fabrica  # accesible para tareas internas y tests
    password = admin_password or os.environ.get("INVENTARIO_ADMIN_PASSWORD")
    if password:
        with fabrica.begin() as s:
            if s.scalar(select(Usuario).where(Usuario.email == admin_email)) is None:
                crear_usuario(s, Usuario, admin_email, "Admin", password, Rol.ADMIN)

    # Los registros públicos entran como LECTOR; el admin los promueve.
    auth = crear_auth(fabrica, Usuario, Token, Rol.LECTOR)
    app.include_router(auth.router)
    sesion_dep = Depends(auth.obtener_sesion)
    cualquiera = Depends(auth.usuario_actual)
    empleado = Depends(auth.requiere_rol(Rol.EMPLEADO, Rol.ADMIN))
    admin = Depends(auth.requiere_rol(Rol.ADMIN))

    @app.exception_handler(servicio.ErrorNegocio)
    async def _err(_r: Request, e: servicio.ErrorNegocio) -> JSONResponse:
        return JSONResponse(status_code=e.codigo, content={"detail": e.mensaje})

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def inicio() -> str:
        """Frontend estático empaquetado dentro del paquete ``app``."""
        return resources.files("app").joinpath("static/index.html").read_text(encoding="utf-8")

    @app.patch("/usuarios/{uid}/rol", dependencies=[admin])
    def cambiar_rol(uid: int, datos: RolIn, s: Session = sesion_dep) -> dict:
        """El admin asigna roles (p. ej. promover un lector a empleado)."""
        u = s.get(Usuario, uid)
        if u is None:
            raise HTTPException(404, "usuario inexistente")
        u.rol = datos.rol
        return {"id": u.id, "rol": u.rol.value}

    # ---- Proveedores ----
    @app.get("/proveedores", response_model=list[ProveedorOut], dependencies=[cualquiera])
    def listar_proveedores(s: Session = sesion_dep) -> list[Proveedor]:
        return list(s.scalars(select(Proveedor).order_by(Proveedor.nombre)))

    @app.post("/proveedores", response_model=ProveedorOut, status_code=201, dependencies=[admin])
    def crear_proveedor(d: ProveedorIn, s: Session = sesion_dep) -> Proveedor:
        p = Proveedor(**d.model_dump())
        s.add(p)
        try:
            s.flush()
        except IntegrityError:
            raise HTTPException(409, "proveedor duplicado") from None
        return p

    # ---- Productos ----
    @app.get("/productos", response_model=list[ProductoOut], dependencies=[cualquiera])
    def listar_productos(q: str = "", s: Session = sesion_dep) -> list[Producto]:
        """Lista productos; ``q`` filtra por nombre o SKU (insensible a mayúsculas)."""
        consulta = select(Producto).order_by(Producto.sku)
        if q:
            patron = f"%{q.lower()}%"
            consulta = consulta.where((Producto.nombre.ilike(patron)) | (Producto.sku.ilike(patron)))
        return list(s.scalars(consulta))

    @app.post("/productos", response_model=ProductoOut, status_code=201, dependencies=[admin])
    def crear_producto(d: ProductoIn, s: Session = sesion_dep) -> Producto:
        if d.proveedor_id is not None and s.get(Proveedor, d.proveedor_id) is None:
            raise HTTPException(404, "proveedor inexistente")
        p = Producto(**d.model_dump(), stock=0)
        s.add(p)
        try:
            s.flush()
        except IntegrityError:
            raise HTTPException(409, "SKU duplicado") from None
        return p

    @app.get("/productos/bajo-minimo", response_model=list[ProductoOut], dependencies=[cualquiera])
    def bajo_minimo(s: Session = sesion_dep) -> list[Producto]:
        return servicio.productos_bajo_minimo(s)

    # ---- Movimientos ----
    @app.post("/movimientos", response_model=MovimientoOut, status_code=201)
    def mover(d: MovimientoIn, u: Usuario = empleado, s: Session = sesion_dep) -> Movimiento:
        return servicio.registrar_movimiento(s, d.producto_id, u.id, d.tipo, d.cantidad, d.motivo)

    @app.get("/productos/{pid}/movimientos", response_model=list[MovimientoOut], dependencies=[cualquiera])
    def historial(pid: int, s: Session = sesion_dep) -> list[Movimiento]:
        return list(s.scalars(select(Movimiento).where(Movimiento.producto_id == pid).order_by(Movimiento.id)))

    # ---- Órdenes de compra ----
    @app.post("/ordenes", status_code=201, dependencies=[admin])
    def nueva_orden(d: OrdenIn, s: Session = sesion_dep) -> dict:
        o = servicio.crear_orden(s, d.proveedor_id, [(l.producto_id, l.cantidad) for l in d.lineas])
        return {"id": o.id, "estado": o.estado.value, "lineas": len(o.lineas)}

    @app.post("/ordenes/{oid}/recibir")
    def recibir(oid: int, u: Usuario = empleado, s: Session = sesion_dep) -> dict:
        o = servicio.recibir_orden(s, oid, u.id)
        return {"id": o.id, "estado": o.estado.value}

    @app.get("/reportes/valor", dependencies=[cualquiera])
    def valor(s: Session = sesion_dep) -> dict:
        return {"valor_centavos": servicio.valor_inventario(s)}

    return app


def __getattr__(nombre: str):  # pragma: no cover - instancia perezosa para uvicorn
    if nombre == "app":
        return crear_app()
    raise AttributeError(nombre)
