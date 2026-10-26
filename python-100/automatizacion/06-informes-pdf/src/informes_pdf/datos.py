"""Capa de datos: consultas SQL de negocio sobre SQLite (DB-API 2.0).

Se usa ``sqlite3`` por ser estándar; como se habla DB-API, cambiar a
PostgreSQL/MySQL sólo requiere otra conexión y ajustar el SQL de fechas.
"""

from __future__ import annotations

import random
import sqlite3
from dataclasses import dataclass

# Esquema mínimo de ventas: precio_unitario se guarda por fila (precio al momento de la venta).
ESQUEMA = """
CREATE TABLE IF NOT EXISTS ventas (
    id INTEGER PRIMARY KEY,
    fecha TEXT NOT NULL,          -- ISO AAAA-MM-DD
    producto TEXT NOT NULL,
    region TEXT NOT NULL,
    unidades INTEGER NOT NULL,
    precio_unitario REAL NOT NULL
);
"""


def crear_base_demo(conn: sqlite3.Connection, filas: int = 500, semilla: int = 42) -> None:
    """Carga datos de ventas sintéticos y reproducibles (semilla fija)."""
    conn.executescript(ESQUEMA)
    # Generador propio con semilla: los mismos datos en cada corrida (tests reproducibles)
    # sin alterar el estado global de ``random``.
    rnd = random.Random(semilla)
    productos = {"Notebook": 950.0, "Monitor": 210.0, "Teclado": 35.0, "Mouse": 18.0, "Auriculares": 60.0}
    regiones = ["Norte", "Sur", "Centro", "Cuyo"]
    datos = []
    for _ in range(filas):
        prod = rnd.choice(list(productos))
        mes = rnd.randint(1, 12)
        # Días 1-28 para que cualquier mes sea válido (febrero incluido) sin calcular calendarios.
        dia = rnd.randint(1, 28)
        datos.append((f"2024-{mes:02d}-{dia:02d}", prod, rnd.choice(regiones), rnd.randint(1, 10), productos[prod]))
    # executemany con parámetros "?" inserta todas las filas en una sola llamada (rápido y seguro).
    conn.executemany(
        "INSERT INTO ventas (fecha, producto, region, unidades, precio_unitario) VALUES (?,?,?,?,?)", datos
    )
    conn.commit()


@dataclass
class Repositorio:
    """Consultas usadas por el informe. Cada método devuelve tuplas simples."""

    conn: sqlite3.Connection

    def kpis(self, desde: str, hasta: str) -> dict[str, float]:
        """Totales del período: facturación, unidades, ticket promedio, operaciones."""
        # COALESCE convierte el NULL de SUM sobre cero filas en 0, así un período vacío devuelve ceros.
        # BETWEEN es inclusivo en ambos extremos.
        fila = self.conn.execute(
            """SELECT COALESCE(SUM(unidades*precio_unitario),0), COALESCE(SUM(unidades),0), COUNT(*)
               FROM ventas WHERE fecha BETWEEN ? AND ?""",
            (desde, hasta),
        ).fetchone()
        # Caso borde: sin operaciones, el ticket promedio es 0.0 en lugar de dividir por cero.
        total, unidades, ops = fila
        return {"facturacion": round(total, 2), "unidades": unidades, "operaciones": ops,
                "ticket_promedio": round(total / ops, 2) if ops else 0.0}

    # substr(fecha, 1, 7) recorta "2024-03-15" a "2024-03": agrupación mensual sin funciones
    # de fecha específicas del motor (portable a otros SQL).
    def ventas_por_mes(self, desde: str, hasta: str) -> list[tuple[str, float]]:
        return self.conn.execute(
            """SELECT substr(fecha,1,7) AS mes, ROUND(SUM(unidades*precio_unitario),2)
               FROM ventas WHERE fecha BETWEEN ? AND ? GROUP BY mes ORDER BY mes""",
            (desde, hasta),
        ).fetchall()

    # Ranking por facturación (no por unidades): un producto caro con pocas ventas puede liderar.
    def top_productos(self, desde: str, hasta: str, n: int = 5) -> list[tuple[str, int, float]]:
        return self.conn.execute(
            """SELECT producto, SUM(unidades), ROUND(SUM(unidades*precio_unitario),2) AS total
               FROM ventas WHERE fecha BETWEEN ? AND ? GROUP BY producto ORDER BY total DESC LIMIT ?""",
            (desde, hasta, n),
        ).fetchall()

    # Orden descendente: el gráfico de barras muestra primero la región que más factura.
    def por_region(self, desde: str, hasta: str) -> list[tuple[str, float]]:
        return self.conn.execute(
            """SELECT region, ROUND(SUM(unidades*precio_unitario),2) AS total
               FROM ventas WHERE fecha BETWEEN ? AND ? GROUP BY region ORDER BY total DESC""",
            (desde, hasta),
        ).fetchall()
