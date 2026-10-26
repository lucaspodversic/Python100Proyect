"""Tests del inventario: roles, movimientos, órdenes y frontend."""
from __future__ import annotations

import threading

from app import servicio
from app.modelos import Producto, TipoMovimiento


def _cab(d):  # quita claves auxiliares de la fixture
    return {k: v for k, v in d.items() if not k.startswith("_")}


def test_frontend_html(c):
    r = c.get("/")
    assert r.status_code == 200 and "Inventario" in r.text and "textContent" in r.text


def test_roles(c, admin, lector, producto):
    l = _cab(lector)
    assert c.get("/productos", headers=l).status_code == 200
    # Un lector no puede mover stock ni crear productos.
    assert c.post("/movimientos", headers=l, json={"producto_id": producto["id"], "tipo": "entrada", "cantidad": 1}).status_code == 403
    assert c.post("/productos", headers=l, json={"sku": "X-1", "nombre": "x", "precio_centavos": 1}).status_code == 403
    # Tras promoverlo a empleado, sí puede mover stock.
    c.patch(f"/usuarios/{lector['_id']}/rol", headers=admin, json={"rol": "empleado"})
    assert c.post("/movimientos", headers=l, json={"producto_id": producto["id"], "tipo": "entrada", "cantidad": 1}).status_code == 201


def test_validaciones_producto(c, admin, producto):
    assert c.post("/productos", headers=admin, json={"sku": "CAF-001", "nombre": "x", "precio_centavos": 1}).status_code == 409
    assert c.post("/productos", headers=admin, json={"sku": "minus", "nombre": "x", "precio_centavos": 1}).status_code == 422
    assert c.post("/productos", headers=admin, json={"sku": "NEG-1", "nombre": "x", "precio_centavos": -1}).status_code == 422
    assert c.post("/productos", headers=admin, json={"sku": "PRV-1", "nombre": "x", "precio_centavos": 1, "proveedor_id": 99}).status_code == 404


def test_movimientos_y_stock_insuficiente(c, empleado, producto):
    pid = producto["id"]
    r = c.post("/movimientos", headers=empleado, json={"producto_id": pid, "tipo": "entrada", "cantidad": 10})
    assert r.json()["stock_resultante"] == 10
    r = c.post("/movimientos", headers=empleado, json={"producto_id": pid, "tipo": "salida", "cantidad": 4, "motivo": "venta"})
    assert r.json()["stock_resultante"] == 6
    r = c.post("/movimientos", headers=empleado, json={"producto_id": pid, "tipo": "salida", "cantidad": 7})
    assert r.status_code == 409  # no hay stock suficiente
    r = c.post("/movimientos", headers=empleado, json={"producto_id": pid, "tipo": "ajuste", "cantidad": 3})
    assert r.json()["stock_resultante"] == 3
    assert c.post("/movimientos", headers=empleado, json={"producto_id": pid, "tipo": "entrada", "cantidad": 0}).status_code == 400
    hist = c.get(f"/productos/{pid}/movimientos", headers=empleado).json()
    assert [m["stock_resultante"] for m in hist] == [10, 6, 3]


def test_bajo_minimo_y_valor(c, empleado, producto):
    assert len(c.get("/productos/bajo-minimo", headers=empleado).json()) == 1
    c.post("/movimientos", headers=empleado, json={"producto_id": producto["id"], "tipo": "entrada", "cantidad": 6})
    assert c.get("/productos/bajo-minimo", headers=empleado).json() == []
    assert c.get("/reportes/valor", headers=empleado).json()["valor_centavos"] == 6 * 450000


def test_ordenes_de_compra(c, admin, empleado, producto):
    pid, prov = producto["id"], producto["proveedor_id"]
    assert c.post("/ordenes", headers=admin, json={"proveedor_id": prov, "lineas": []}).status_code == 400
    assert c.post("/ordenes", headers=admin, json={"proveedor_id": prov, "lineas": [
        {"producto_id": pid, "cantidad": 1}, {"producto_id": pid, "cantidad": 2}]}).status_code == 400
    oid = c.post("/ordenes", headers=admin, json={"proveedor_id": prov, "lineas": [{"producto_id": pid, "cantidad": 20}]}).json()["id"]
    assert c.post(f"/ordenes/{oid}/recibir", headers=empleado).json()["estado"] == "recibida"
    # Recibir dos veces no duplica el stock.
    assert c.post(f"/ordenes/{oid}/recibir", headers=empleado).status_code == 409
    prods = c.get("/productos", params={"q": "café"}, headers=empleado).json()
    assert prods[0]["stock"] == 20


def test_ventas_concurrentes_no_dejan_stock_negativo(app, c, empleado, producto):
    """20 hilos intentan vender 1 unidad con stock 5: exactamente 5 lo logran."""
    c.post("/movimientos", headers=empleado, json={"producto_id": producto["id"], "tipo": "entrada", "cantidad": 5})
    fabrica = app.state.fabrica
    ok, fallos = [], []
    barrera = threading.Barrier(20)  # todos los hilos arrancan a la vez

    def vender() -> None:
        barrera.wait()
        try:
            with fabrica.begin() as s:
                servicio.registrar_movimiento(s, producto["id"], 1, TipoMovimiento.SALIDA, 1)
            ok.append(1)
        except servicio.ErrorNegocio:
            fallos.append(1)

    hilos = [threading.Thread(target=vender) for _ in range(20)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert len(ok) == 5 and len(fallos) == 15
    with fabrica() as s:
        assert s.get(Producto, producto["id"]).stock == 0
