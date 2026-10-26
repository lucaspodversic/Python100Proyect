"""Reglas de negocio del inventario (sin dependencia de HTTP)."""
from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .modelos import (EstadoOrden, LineaOrden, Movimiento, OrdenCompra, Producto,
                      Proveedor, TipoMovimiento)


class ErrorNegocio(Exception):
    """Violación de una regla de negocio; ``codigo`` es el estado HTTP sugerido."""

    def __init__(self, mensaje: str, codigo: int = 400) -> None:
        super().__init__(mensaje)
        self.mensaje, self.codigo = mensaje, codigo


def registrar_movimiento(sesion: Session, producto_id: int, usuario_id: int,
                         tipo: TipoMovimiento, cantidad: int, motivo: str = "") -> Movimiento:
    """Aplica un movimiento de stock de forma atómica y lo deja auditado.

    Para las salidas se usa un ``UPDATE ... WHERE stock >= cantidad``: la
    comprobación y la resta ocurren en una sola sentencia SQL, por lo que dos
    ventas simultáneas nunca pueden dejar el stock en negativo.
    """
    if tipo != TipoMovimiento.AJUSTE and cantidad <= 0:
        raise ErrorNegocio("la cantidad debe ser positiva")
    if tipo == TipoMovimiento.AJUSTE and cantidad < 0:
        raise ErrorNegocio("el stock ajustado no puede ser negativo")
    if sesion.get(Producto, producto_id) is None:
        raise ErrorNegocio("producto inexistente", 404)

    if tipo == TipoMovimiento.ENTRADA:
        sentencia = update(Producto).where(Producto.id == producto_id).values(stock=Producto.stock + cantidad)
    elif tipo == TipoMovimiento.SALIDA:
        sentencia = (update(Producto)
                     .where(Producto.id == producto_id, Producto.stock >= cantidad)
                     .values(stock=Producto.stock - cantidad))
    else:  # AJUSTE: fija el valor contado físicamente
        sentencia = update(Producto).where(Producto.id == producto_id).values(stock=cantidad)

    resultado = sesion.execute(sentencia.execution_options(synchronize_session=False))
    if resultado.rowcount == 0:
        raise ErrorNegocio("stock insuficiente", 409)
    # Releemos el valor real desde la BD (el objeto en memoria podría estar desfasado).
    stock = sesion.scalar(select(Producto.stock).where(Producto.id == producto_id))
    # Sincronizamos el objeto en memoria con la BD para respuestas coherentes.
    sesion.refresh(sesion.get(Producto, producto_id))
    mov = Movimiento(producto_id=producto_id, usuario_id=usuario_id, tipo=tipo,
                     cantidad=cantidad, stock_resultante=stock, motivo=motivo)
    sesion.add(mov)
    sesion.flush()
    return mov


def productos_bajo_minimo(sesion: Session) -> list[Producto]:
    """Productos cuyo stock está en o por debajo del mínimo (para reponer)."""
    return list(sesion.scalars(select(Producto).where(Producto.stock <= Producto.stock_minimo)
                               .order_by(Producto.sku)))


def crear_orden(sesion: Session, proveedor_id: int, lineas: list[tuple[int, int]]) -> OrdenCompra:
    """Crea una orden de compra validando proveedor, productos y cantidades."""
    if sesion.get(Proveedor, proveedor_id) is None:
        raise ErrorNegocio("proveedor inexistente", 404)
    if not lineas:
        raise ErrorNegocio("la orden debe tener al menos una línea")
    vistos: set[int] = set()
    orden = OrdenCompra(proveedor_id=proveedor_id)
    for producto_id, cantidad in lineas:
        if cantidad <= 0:
            raise ErrorNegocio("cantidades positivas únicamente")
        if producto_id in vistos:
            raise ErrorNegocio("producto repetido en la orden")
        if sesion.get(Producto, producto_id) is None:
            raise ErrorNegocio(f"producto {producto_id} inexistente", 404)
        vistos.add(producto_id)
        orden.lineas.append(LineaOrden(producto_id=producto_id, cantidad=cantidad))
    sesion.add(orden)
    sesion.flush()
    return orden


def recibir_orden(sesion: Session, orden_id: int, usuario_id: int) -> OrdenCompra:
    """Marca la orden como recibida y suma cada línea al stock (con movimiento)."""
    orden = sesion.get(OrdenCompra, orden_id)
    if orden is None:
        raise ErrorNegocio("orden inexistente", 404)
    if orden.estado != EstadoOrden.PENDIENTE:
        # Evita sumar dos veces el mismo pedido.
        raise ErrorNegocio(f"la orden está {orden.estado.value}", 409)
    for linea in orden.lineas:
        registrar_movimiento(sesion, linea.producto_id, usuario_id, TipoMovimiento.ENTRADA,
                             linea.cantidad, f"orden de compra #{orden.id}")
    orden.estado = EstadoOrden.RECIBIDA
    return orden


def valor_inventario(sesion: Session) -> int:
    """Valor total del inventario en centavos (stock × precio)."""
    return sum(p.stock * p.precio_centavos for p in sesion.scalars(select(Producto)))
