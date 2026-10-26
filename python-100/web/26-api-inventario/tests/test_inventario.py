"""Tests del servicio y de la API de inventario."""
import pytest
from fastapi.testclient import TestClient

from inventario.app import crear_app
from inventario.servicio import ErrorInventario, Inventario


@pytest.fixture()
# Producto 1 = TORN-01 con punto de reorden 10; almacén 1 = Central, 2 = Sucursal.
def inv():
    i = Inventario()
    i.crear_producto("TORN-01", "Tornillo", punto_reorden=10)
    i.crear_almacen("Central")
    i.crear_almacen("Sucursal")
    return i


# (10 x 100 + 30 x 200) / 40 = 7000 / 40 = 175; valor = 40 x 175 = 7000.
def test_costo_promedio_ponderado(inv):
    inv.entrada(1, 1, 10, 100.0)
    inv.entrada(1, 1, 30, 200.0)
    s = inv.stock_producto(1)
    assert s["total"] == 40 and s["costo_promedio"] == pytest.approx(175.0)
    assert s["valor"] == 7000.0


# Hay 5 y se intenta sacar 6: 409 y el stock queda intacto.
def test_salida_no_deja_negativo(inv):
    inv.entrada(1, 1, 5, 1)
    with pytest.raises(ErrorInventario) as e:
        inv.salida(1, 1, 6)
    assert e.value.codigo == 409
    assert inv.total_producto(1) == 5


# 8 en Central, se pasan 3: quedan 5 y 3. Luego se intenta pasar 99 desde
# Sucursal (tiene 3): falla y ningún almacén cambia.
def test_transferencia_atomica(inv):
    inv.entrada(1, 1, 8, 1)
    assert inv.transferir(1, 1, 2, 3) == {"origen": 5, "destino": 3}
    with pytest.raises(ErrorInventario):
        inv.transferir(1, 2, 1, 99)  # falla: ningún almacén cambia
    assert inv.stock_producto(1)["por_almacen"] == {"Central": 5, "Sucursal": 3}


# Entrada 10 -> salida 4 (saldo 6) -> conteo físico 5 (ajuste -1).
def test_ajuste_requiere_nota_y_kardex(inv):
    inv.entrada(1, 1, 10, 2)
    inv.salida(1, 1, 4)
    with pytest.raises(ErrorInventario):
        inv.ajuste(1, 1, 5, "")
    inv.ajuste(1, 1, 5, "conteo anual")
    k = inv.kardex(1)
    assert [m["tipo"] for m in k] == ["ENTRADA", "SALIDA", "AJUSTE"]
    assert [m["saldo"] for m in k] == [10, 6, 5]


# Tuerca: 50 >= 2, no alerta. Tornillo: 4 <= 10, alerta y
# a_pedir = 10 x 2 - 4 = 16.
def test_bajo_stock(inv):
    inv.crear_producto("TUER-01", "Tuerca", punto_reorden=2)
    inv.entrada(2, 1, 50, 1)
    inv.entrada(1, 1, 4, 1)
    alertas = inv.bajo_stock()
    assert [a["sku"] for a in alertas] == ["TORN-01"] and alertas[0]["a_pedir"] == 16


# "torn-01" se normaliza a "TORN-01", que ya existe; producto 99 => 404.
def test_duplicados_e_inexistentes(inv):
    with pytest.raises(ErrorInventario):
        inv.crear_producto("torn-01", "otro")  # SKU se normaliza a mayúsculas
    with pytest.raises(ErrorInventario) as e:
        inv.entrada(99, 1, 1, 1)
    assert e.value.codigo == 404


# Recorre la API entera: 10 cables a $3 en A, salida imposible de 20 (409),
# transferencia de 4 a B => A:6, B:4. Valuación = 10 x 3 = 30. Stock 10 >
# punto de reorden 5 => sin alertas. Kardex: 1 entrada + 2 de transferencia.
def test_api_flujo_completo():
    c = TestClient(crear_app())
    pid = c.post("/productos", json={"sku": "CAB-1", "nombre": "Cable", "punto_reorden": 5}).json()["id"]
    a1 = c.post("/almacenes", json={"nombre": "A"}).json()["id"]
    a2 = c.post("/almacenes", json={"nombre": "B"}).json()["id"]
    assert c.post("/movimientos/entrada", json={"producto_id": pid, "almacen_id": a1, "cantidad": 10,
                                                 "costo_unitario": 3}).json() == {"stock": 10}
    assert c.post("/movimientos/salida", json={"producto_id": pid, "almacen_id": a1, "cantidad": 20}).status_code == 409
    c.post("/movimientos/transferencia", json={"producto_id": pid, "origen": a1, "destino": a2, "cantidad": 4})
    assert c.get(f"/productos/{pid}/stock").json()["por_almacen"] == {"A": 6, "B": 4}
    assert c.get("/reportes/valuacion").json() == {"valor_total": 30.0}
    assert c.get("/alertas/bajo-stock").json() == []
    assert len(c.get(f"/productos/{pid}/kardex").json()) == 3
    assert c.post("/productos", json={"sku": "con espacio", "nombre": "x"}).status_code == 422
    assert c.get("/productos/999/stock").status_code == 404
