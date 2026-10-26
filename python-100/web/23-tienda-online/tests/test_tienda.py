"""Tests end-to-end de catálogo, carrito y checkout."""
import pytest
from fastapi.testclient import TestClient

from tienda.app import crear_app
from tienda.pagos import PasarelaSimulada

# Token que se le pasa a crear_app en la fixture.
ADMIN = {"X-Admin-Token": "secreto-test"}
TARJETA_OK = {"numero_tarjeta": "4242424242424242", "cvv": "123", "vencimiento": "12/99"}


@pytest.fixture()
# Catálogo base: Mate $15,00 (stock 5) y Bombilla $8,00 (stock 1, para
# poder probar el agotamiento con una sola compra).
def entorno():
    pasarela = PasarelaSimulada()
    c = TestClient(crear_app(":memory:", pasarela, token_admin="secreto-test"))
    p1 = c.post("/productos", json={"nombre": "Mate", "precio_centavos": 1500, "stock": 5}, headers=ADMIN).json()
    p2 = c.post("/productos", json={"nombre": "Bombilla", "precio_centavos": 800, "stock": 1}, headers=ADMIN).json()
    return c, pasarela, p1["id"], p2["id"]


# Sin header y con header incorrecto: ambos 401.
def test_admin_requiere_token(entorno):
    c, *_ = entorno
    assert c.post("/productos", json={"nombre": "x", "precio_centavos": 1, "stock": 1}).status_code == 401
    assert c.post("/productos", json={"nombre": "x", "precio_centavos": 1, "stock": 1},
                  headers={"X-Admin-Token": "mal"}).status_code == 401


def test_carrito_total_y_stock(entorno):
    c, _, p1, p2 = entorno
    cid = c.post("/carritos").json()["id"]
    c.put(f"/carritos/{cid}/items", json={"producto_id": p1, "cantidad": 2})
    det = c.put(f"/carritos/{cid}/items", json={"producto_id": p2, "cantidad": 1}).json()
    # 2 mates (2 x 1500) + 1 bombilla (800) = 3800 centavos.
    assert det["total_centavos"] == 2 * 1500 + 800
    # Pedir 2 bombillas con stock 1 -> 409.
    assert c.put(f"/carritos/{cid}/items", json={"producto_id": p2, "cantidad": 2}).status_code == 409
    det = c.delete(f"/carritos/{cid}/items/{p2}").json()
    # Sin la bombilla quedan los 2 mates: 3000.
    assert det["total_centavos"] == 3000


def test_checkout_exitoso_descuenta_stock_y_no_guarda_tarjeta(entorno):
    c, pasarela, p1, _ = entorno
    cid = c.post("/carritos").json()["id"]
    c.put(f"/carritos/{cid}/items", json={"producto_id": p1, "cantidad": 3})
    r = c.post(f"/carritos/{cid}/checkout", json=TARJETA_OK)
    assert r.status_code == 201
    pedido = r.json()
    # 3 mates x 1500 = 4500; la respuesta no contiene el número completo.
    assert pedido["total_centavos"] == 4500 and pedido["ultimos4"] == "4242"
    assert "4242424242424242" not in str(pedido)
    assert pasarela.cobros[pedido["transaccion"]] == 4500
    stock = {p["id"]: p["stock"] for p in c.get("/productos").json()}
    # Stock inicial 5 - 3 vendidos = 2.
    assert stock[p1] == 2
    # El carrito queda cerrado
    assert c.put(f"/carritos/{cid}/items", json={"producto_id": p1, "cantidad": 1}).status_code == 409


# 4000000000000002 = "Tarjeta rechazada": 402 y el stock sigue en 5.
def test_pago_rechazado_no_toca_stock(entorno):
    c, _, p1, _ = entorno
    cid = c.post("/carritos").json()["id"]
    c.put(f"/carritos/{cid}/items", json={"producto_id": p1, "cantidad": 1})
    r = c.post(f"/carritos/{cid}/checkout", json={**TARJETA_OK, "numero_tarjeta": "4000000000000002"})
    assert r.status_code == 402 and r.json()["detail"] == "Tarjeta rechazada"
    assert c.get("/productos").json()[0]["stock"] == 5


# Misma Idempotency-Key dos veces: mismo pedido y un solo cobro registrado.
def test_checkout_idempotente(entorno):
    c, pasarela, p1, _ = entorno
    cid = c.post("/carritos").json()["id"]
    c.put(f"/carritos/{cid}/items", json={"producto_id": p1, "cantidad": 1})
    h = {"Idempotency-Key": "abc-123"}
    a = c.post(f"/carritos/{cid}/checkout", json=TARJETA_OK, headers=h).json()
    b = c.post(f"/carritos/{cid}/checkout", json=TARJETA_OK, headers=h).json()
    assert a["id"] == b["id"] and len(pasarela.cobros) == 1


# Checkout sin ítems -> 400; carrito inventado -> 404.
def test_carrito_vacio_e_inexistente(entorno):
    c, *_ = entorno
    cid = c.post("/carritos").json()["id"]
    assert c.post(f"/carritos/{cid}/checkout", json=TARJETA_OK).status_code == 400
    assert c.get("/carritos/noexiste").status_code == 404


# Dos carritos con la única bombilla: el primero que paga gana, el segundo
# recibe 409 gracias a la revalidación de stock en el checkout.
def test_stock_cambia_entre_carrito_y_pago(entorno):
    c, _, _, p2 = entorno
    a, b = c.post("/carritos").json()["id"], c.post("/carritos").json()["id"]
    c.put(f"/carritos/{a}/items", json={"producto_id": p2, "cantidad": 1})
    c.put(f"/carritos/{b}/items", json={"producto_id": p2, "cantidad": 1})
    assert c.post(f"/carritos/{a}/checkout", json=TARJETA_OK).status_code == 201
    assert c.post(f"/carritos/{b}/checkout", json=TARJETA_OK).status_code == 409


# Borrado lógico: 204 y deja de aparecer en el catálogo público.
def test_producto_desactivado_no_se_lista(entorno):
    c, _, p1, _ = entorno
    assert c.delete(f"/productos/{p1}", headers=ADMIN).status_code == 204
    assert all(p["id"] != p1 for p in c.get("/productos").json())
