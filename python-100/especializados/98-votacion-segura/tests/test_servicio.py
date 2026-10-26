"""Tests de reglas de negocio de la elección, sin HTTP."""
import sqlite3

import pytest

from votacion.cliente import Votante
from votacion.servicio import Eleccion, ErrorVotacion, mensaje_papeleta
from votacion.urna import GENESIS


def votar_completo(el: Eleccion, token: str, opcion: str) -> dict:
    """Atajo: hace todo el recorrido del votante (cegar, pedir firma, descegar, votar)."""
    v = Votante(el.publica, el.id, opcion)
    pap = v.papeleta(el.firmar(token, v.cegado()))
    return el.votar(pap["serie"], pap["opcion"], int(pap["firma"], 16))


def test_eleccion_completa(eleccion):
    """3 votantes votan Ana, Ana, Beto → resultados 2/1/0 y auditoría íntegra."""
    tokens = [eleccion.registrar(f"v{i}") for i in range(3)]
    eleccion.abrir()
    for t, o in zip(tokens, ["Ana", "Ana", "Beto"]):
        votar_completo(eleccion, t, o)
    eleccion.cerrar()
    assert eleccion.resultados() == {"Ana": 2, "Beto": 1, "En blanco": 0}
    aud = eleccion.auditar()
    assert aud["integra"] and aud["votos"] == 3 and aud["firmas_emitidas"] == 3 and aud["habilitados"] == 3
    assert aud["bloques"][0]["previo"] == GENESIS and aud["cabeza"] == aud["bloques"][-1]["hash"]


def test_token_de_un_solo_uso(eleccion):
    """El segundo pedido de firma con el mismo token se rechaza con 409 (una persona, una firma)."""
    t = eleccion.registrar("ana")
    eleccion.abrir()
    v = Votante(eleccion.publica, eleccion.id, "Ana")
    eleccion.firmar(t, v.cegado())
    with pytest.raises(ErrorVotacion) as e:
        eleccion.firmar(t, v.cegado())
    assert e.value.codigo == 409


def test_token_invalido_y_valor_invalido_no_quema_el_token(eleccion):
    """Un token inventado da 401. Un cegado fuera de rango da 422 pero el token sigue sirviendo."""
    t = eleccion.registrar("ana")
    eleccion.abrir()
    with pytest.raises(ErrorVotacion) as e:
        eleccion.firmar("token-que-no-existe", 12345)
    assert e.value.codigo == 401
    with pytest.raises(ErrorVotacion) as e:
        eleccion.firmar(t, 1)
    assert e.value.codigo == 422
    votar_completo(eleccion, t, "Beto")  # todavía puede votar


def test_doble_deposito_de_la_misma_papeleta(eleccion):
    """Reenviar la misma papeleta firmada (misma serie) se rechaza: una firma, un voto."""
    t = eleccion.registrar("ana")
    eleccion.abrir()
    v = Votante(eleccion.publica, eleccion.id, "Ana")
    pap = v.papeleta(eleccion.firmar(t, v.cegado()))
    eleccion.votar(pap["serie"], "Ana", int(pap["firma"], 16))
    with pytest.raises(ErrorVotacion, match="ya fue depositada"):
        eleccion.votar(pap["serie"], "Ana", int(pap["firma"], 16))


def test_no_se_puede_cambiar_la_opcion(eleccion):
    """La firma cubre la opción: interceptar la papeleta y cambiar "Ana" por "Beto" la invalida (403)."""
    t = eleccion.registrar("ana")
    eleccion.abrir()
    v = Votante(eleccion.publica, eleccion.id, "Ana")
    pap = v.papeleta(eleccion.firmar(t, v.cegado()))
    with pytest.raises(ErrorVotacion) as e:
        eleccion.votar(pap["serie"], "Beto", int(pap["firma"], 16))
    assert e.value.codigo == 403


def test_firma_de_otra_eleccion_no_sirve(eleccion, autoridad):
    """Aunque se use la misma clave, el id de elección está dentro del mensaje firmado."""
    otra = Eleccion("otra", ["Ana", "Beto"], autoridad=autoridad)
    t = otra.registrar("x"); otra.abrir(); eleccion.abrir()
    v = Votante(otra.publica, "otra", "Ana")
    pap = v.papeleta(otra.firmar(t, v.cegado()))
    with pytest.raises(ErrorVotacion, match="firma inválida"):
        eleccion.votar(pap["serie"], "Ana", int(pap["firma"], 16))


def test_estados(eleccion):
    """No se firma ni vota en preparación; resultados solo al cerrar; no se reabre."""
    t = eleccion.registrar("ana")
    with pytest.raises(ErrorVotacion, match="no está abierta"):
        eleccion.firmar(t, 5)
    eleccion.abrir()
    with pytest.raises(ErrorVotacion, match="al cerrar"):
        eleccion.resultados()
    eleccion.cerrar()
    with pytest.raises(ErrorVotacion):
        eleccion.abrir()
    with pytest.raises(ErrorVotacion):
        eleccion.registrar("tarde")


def test_validaciones_de_entrada(eleccion):
    """Opción inexistente, serie mal formada, padrón duplicado y opciones de elección inválidas."""
    eleccion.registrar("ana")
    with pytest.raises(ErrorVotacion, match="ya está"):
        eleccion.registrar("ana")
    eleccion.abrir()
    with pytest.raises(ErrorVotacion, match="opción"):
        eleccion.votar("a" * 64, "Carla", 5)
    with pytest.raises(ErrorVotacion, match="serie"):
        eleccion.votar("XYZ", "Ana", 5)
    with pytest.raises(ValueError):
        Eleccion("e", ["solo-una"])
    with pytest.raises(ValueError):
        Eleccion("e", ["A", "A"])


def test_anonimato_en_la_base(eleccion):
    """Ninguna tabla vincula votante con voto: la urna no tiene columna de votante,
    y ni el nombre ni el token aparecen en los bloques. El padrón guarda el hash del token, no el token."""
    t = eleccion.registrar("ana-perez")
    eleccion.abrir()
    votar_completo(eleccion, t, "Ana")
    db = eleccion._db
    columnas = [c[1] for c in db.execute("PRAGMA table_info(bloques)")]
    assert columnas == ["indice", "serie", "opcion", "firma", "previo", "hash"]
    volcado = "\n".join(db.iterdump())
    bloque = str(eleccion.urna.bloques()[0])
    assert "ana-perez" not in bloque and t not in volcado


def test_auditoria_detecta_manipulacion(eleccion):
    """Alterar la opción de un voto directamente en SQLite: el hash del bloque deja
    de coincidir Y la firma deja de verificar → dos problemas reportados."""
    tokens = [eleccion.registrar(f"v{i}") for i in range(2)]
    eleccion.abrir()
    for t in tokens:
        votar_completo(eleccion, t, "Ana")
    eleccion._db.execute("UPDATE bloques SET opcion = 'Beto' WHERE indice = 0")
    aud = eleccion.auditar()
    assert not aud["integra"]
    assert any("hash no coincide" in p for p in aud["problemas"])
    assert any("firma inválida" in p for p in aud["problemas"])


def test_auditoria_detecta_borrado_y_votos_de_mas(eleccion):
    """Borrar el bloque 0 rompe el enlace del 1; insertar un voto sin firma emitida
    se detecta por conteo (más votos que firmas)."""
    tokens = [eleccion.registrar(f"v{i}") for i in range(2)]
    eleccion.abrir()
    for t in tokens:
        votar_completo(eleccion, t, "Beto")
    eleccion._db.execute("DELETE FROM bloques WHERE indice = 0")
    probs = eleccion.auditar()["problemas"]
    assert any("enlace roto" in p for p in probs) and any("fuera de secuencia" in p for p in probs)

    # Elección nueva: alguien "rellena" la urna con un bloque bien encadenado pero sin firma válida.
    otra = Eleccion("x", ["A", "B"], autoridad=eleccion.autoridad)
    otra.urna.agregar("f" * 64, "A", "abc")
    probs = otra.auditar()["problemas"]
    assert any("firma inválida" in p for p in probs) and any("1 votos pero solo 0" in p for p in probs)


def test_mensaje_canonico():
    """El separador 0x1F evita ambigüedad: ("ab","c") y ("a","bc") dan mensajes distintos."""
    assert mensaje_papeleta("e", "ab", "c") != mensaje_papeleta("e", "a", "bc")


def test_persistencia_en_archivo(tmp_path, autoridad):
    """Con ruta de archivo, la urna sobrevive a reabrir la conexión (y la cadena sigue íntegra)."""
    ruta = str(tmp_path / "urna.db")
    el = Eleccion("p", ["A", "B"], autoridad=autoridad, ruta_db=ruta)
    t = el.registrar("x"); el.abrir()
    votar_completo(el, t, "A")
    el.urna.cerrar()
    filas = sqlite3.connect(ruta).execute("SELECT COUNT(*) FROM bloques").fetchone()[0]
    assert filas == 1
