"""Crea una base de ejemplo (tienda) para probar el traductor."""
import sqlite3
from pathlib import Path


def crear_base_demo(ruta: str | Path) -> None:
    # Datos chicos y conocidos: los totales esperados en los tests salen de acá
    # (Mate 3500, Termo 25000, Yerba 4200; 4 pedidos).
    con = sqlite3.connect(ruta)
    con.executescript("""
    CREATE TABLE clientes (id INTEGER PRIMARY KEY, nombre TEXT, ciudad TEXT, password_hash TEXT);
    CREATE TABLE productos (id INTEGER PRIMARY KEY, nombre TEXT, categoria TEXT, precio REAL);
    CREATE TABLE pedidos (id INTEGER PRIMARY KEY, cliente_id INTEGER REFERENCES clientes(id),
                          producto_id INTEGER REFERENCES productos(id), cantidad INTEGER, fecha TEXT);
    INSERT INTO clientes VALUES (1,'Ana','Córdoba','h1'),(2,'Beto','Rosario','h2'),(3,'Caro','Córdoba','h3');
    INSERT INTO productos VALUES (1,'Mate','Bazar',3500),(2,'Termo','Bazar',25000),(3,'Yerba','Almacén',4200);
    INSERT INTO pedidos VALUES (1,1,1,2,'2026-10-01'),(2,1,3,5,'2026-10-03'),(3,2,2,1,'2026-10-05'),
                               (4,3,3,3,'2026-10-07');
    """)
    con.commit(); con.close()
