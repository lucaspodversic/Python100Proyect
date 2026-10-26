# 72 · Gestor de inventario para una tienda

Aplicación **full-stack** liviana: API REST con **FastAPI + SQLAlchemy + SQLite** y un frontend HTML/JS sin frameworks, servido por la API en `/`. Gestiona productos, stock, proveedores y órdenes de compra.

## Qué demuestra

- **Stock sin carreras**: las salidas usan `UPDATE ... SET stock = stock - n WHERE stock >= n`, que compara y resta en una sola sentencia. Además hay un `CHECK (stock >= 0)` en la tabla. Un test lanza 20 ventas simultáneas sobre un stock de 5 y verifica que se concretan exactamente 5.
- **Auditoría**: cada cambio de stock queda como `Movimiento` con usuario, tipo, cantidad y stock resultante.
- **Roles**: `lector` solo consulta, `empleado` mueve stock y recibe órdenes, `admin` gestiona catálogo, proveedores y roles. Al registrarse, todo usuario entra como `lector`.
- **Órdenes de compra**: al recibirlas se suma el stock una sola vez; repetir la recepción devuelve 409.
- Reportes: productos bajo el mínimo y valor total del inventario.
- Frontend seguro: el token queda en memoria (no en `localStorage`) y los datos se pintan con `textContent`, lo que evita XSS.

## Arquitectura

```
app/
├── db.py, seguridad.py, auth.py   # infraestructura: BD, contraseñas/tokens, roles
├── modelos.py                     # Producto, Proveedor, Movimiento, OrdenCompra...
├── servicio.py                    # reglas de negocio (atómicas)
├── main.py                        # rutas + crear_app()
└── static/index.html              # frontend
```

Rutas principales: `/auth/registro`, `/auth/login`, `PATCH /usuarios/{id}/rol`, `/proveedores`, `/productos?q=`, `/productos/bajo-minimo`, `/movimientos`, `/productos/{id}/movimientos`, `/ordenes`, `/ordenes/{id}/recibir`, `/reportes/valor`.

## Instalación

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Uso

```bash
export INVENTARIO_ADMIN_PASSWORD="clave-segura"    # admin inicial: admin@tienda.local
uvicorn app.main:app --reload
# Frontend: http://127.0.0.1:8000/   ·   Documentación: http://127.0.0.1:8000/docs
```

## Tests

```bash
pytest
```

## Limitaciones

- El frontend es mínimo: lista, busca e inicia sesión. Las altas se hacen desde `/docs`.
- No maneja multi-almacén, lotes ni vencimientos.
- Los tokens no expiran.
