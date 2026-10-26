"""Tests de NL->SQL: validador, autorizador, solo lectura y reintento. Sin red."""
import sqlite3

import pytest

from nlsql.demo import crear_base_demo
from nlsql.ejecutor import ConsultaRechazada, conectar_solo_lectura, ejecutar
from nlsql.esquema import describir_esquema
from nlsql.llm import ProveedorFalso
from nlsql.traductor import TraductorNLSQL
from nlsql.validador import SQLInvalido, extraer_sql, validar_select

OCULTAS = {"clientes.password_hash"}


@pytest.fixture()
def con(tmp_path):
    ruta = tmp_path / "tienda.db"
    crear_base_demo(ruta)
    c = conectar_solo_lectura(ruta)
    yield c
    c.close()


@pytest.mark.parametrize("sql", [
    "DELETE FROM clientes",
    "SELECT 1; DROP TABLE clientes",
    # Truco: el ";" queda antes de un comentario y otro después; al quitar el
    # comentario igual quedan ";" en el medio => rechazado.
    "select * from clientes;-- \n; update clientes set nombre='x'",
    "PRAGMA table_info(clientes)",
    "ATTACH DATABASE 'x.db' AS x",
    # Empieza con WITH pero escribe: lo frena la palabra "delete".
    "WITH t AS (SELECT 1) DELETE FROM clientes",
    "UPDATE clientes SET nombre = 'a'",
    "",
])
def test_validador_rechaza(sql):
    with pytest.raises(SQLInvalido):
        validar_select(sql)


def test_validador_acepta_y_agrega_limit():
    assert validar_select("SELECT nombre FROM clientes;", 10) == "SELECT * FROM (SELECT nombre FROM clientes) LIMIT 10"
    # Si ya trae LIMIT al final, se respeta tal cual.
    assert validar_select("SELECT 1 LIMIT 5") == "SELECT 1 LIMIT 5"
    # palabras prohibidas DENTRO de strings no molestan
    assert "Drop" in validar_select("SELECT * FROM productos WHERE nombre = 'Drop; delete'")
    assert validar_select("WITH c AS (SELECT 1 AS x) SELECT x FROM c").startswith("SELECT * FROM (WITH")


def test_extraer_sql():
    assert extraer_sql("Acá va:\n```sql\nSELECT 1\n```") == "SELECT 1"


def test_esquema_oculta_columnas(con):
    e = describir_esquema(con, OCULTAS)
    assert "TABLE pedidos" in e and "FK: cliente_id -> clientes.id, producto_id -> productos.id" in e
    # Ni la columna ni sus valores de ejemplo ('h1') llegan al LLM.
    assert "password_hash" not in e and "'h1'" not in e


def test_autorizador_bloquea_columna_sensible(con):
    with pytest.raises(ConsultaRechazada, match="password_hash"):
        ejecutar(con, "SELECT password_hash FROM clientes", OCULTAS)
    # SELECT * también intenta leerla -> bloqueado
    with pytest.raises(ConsultaRechazada):
        ejecutar(con, "SELECT * FROM clientes", OCULTAS)


def test_conexion_es_solo_lectura(con):
    # Aunque se saltara el validador y el autorizador, la conexión rechaza escrituras
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        con.execute("INSERT INTO productos VALUES (9,'x','y',1)")


def test_timeout(con):
    # CTE recursiva infinita: sin el corte por tiempo no terminaría nunca.
    lenta = "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n) SELECT count(*) FROM n"
    with pytest.raises(ConsultaRechazada, match="tiempo"):
        ejecutar(con, lenta, segundos_max=0.2)


def test_traduccion_completa(con):
    sql = ("```sql\nSELECT c.ciudad, SUM(p.cantidad * pr.precio) AS total FROM pedidos p "
           "JOIN clientes c ON c.id = p.cliente_id JOIN productos pr ON pr.id = p.producto_id "
           "GROUP BY c.ciudad ORDER BY total DESC\n```")
    llm = ProveedorFalso(respuestas=[sql])
    r = TraductorNLSQL(con, llm, OCULTAS).preguntar("¿Cuánto se vendió por ciudad?")
    assert r.error is None and r.columnas == ["ciudad", "total"]
    # Córdoba: Ana 2 mates (2 x 3500 = 7000) + 5 yerbas (5 x 4200 = 21000) y
    # Caro 3 yerbas (12600) => 40600. Rosario: Beto 1 termo => 25000.
    assert r.filas == [("Córdoba", 40600.0), ("Rosario", 25000.0)]
    assert "TABLE productos" in llm.llamadas[0][0].contenido


def test_reintento_con_error(con):
    # Primer intento inválido (DELETE); el segundo cuenta los 4 pedidos de la demo.
    llm = ProveedorFalso(respuestas=["DELETE FROM pedidos", "SELECT COUNT(*) AS n FROM pedidos"])
    r = TraductorNLSQL(con, llm, OCULTAS).preguntar("¿cuántos pedidos hay?")
    assert r.intentos == 2 and r.filas == [(4,)]
    assert "SQLInvalido" in llm.llamadas[1][-1].contenido


# El falso responde siempre lo mismo (bloqueado): tras 2 intentos se
# devuelve el error, sin filas.
def test_falla_tras_reintentos(con):
    r = TraductorNLSQL(con, ProveedorFalso(respuestas=["SELECT password_hash FROM clientes"]), OCULTAS).preguntar("x")
    assert r.filas == [] and "Bloqueado" in r.error
